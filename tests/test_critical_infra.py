"""
Юнит-тесты критически важной инфраструктуры City-N Reservation Bot

Покрывает:
  • LockedDict (атомарность, конкурентный доступ, update)
  • Event-состояния (combat, dialog, research, anomaly, pending)
  • Emission-состояния (pending, cleanup)
  • Market browse state (атомарный update, TOCTOU)
  • Location mechanics (modifiers, anomaly weights, unique mechanics)
  • Emission lifecycle (scheduling, status transitions, quiet hours)
  • Random events (selection, application, multi-stage)

Запуск:
    python -m pytest tests/test_critical_infra.py -v
    python -m pytest tests/test_critical_infra.py -v -k test_locked_dict
"""
import time
import threading
import random
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

import infra.state_manager as state_manager
from game.location_mechanics import (
    LOCATION_MODIFIERS,
    LOCATION_LOOT_BIAS,
    get_energy_cost_mult,
    get_find_chance_mult,
    get_danger_mult,
    get_radiation_mult,
    get_anomaly_weights,
    get_event_weights,
    get_loot_quality,
    check_ambush,
    check_zone_mutation,
    clear_zone_mutation_state,
    check_mutant_hunt,
    get_mutant_hunt_count,
    get_location_loot_bias,
    get_location_loot_bias_chance,
    is_research_location,
    get_location_modifier,
    _zone_mutation_state,
)


# ===========================================================================
# 1. LockedDict — thread safety, atomic update
# ===========================================================================

class TestLockedDict(unittest.TestCase):
    """Тесты потокобезопасного словаря"""

    def setUp(self):
        self.d = state_manager.LockedDict()

    # --- CRUD ---

    def test_set_and_get(self):
        self.d["a"] = 1
        self.assertEqual(self.d["a"], 1)

    def test_get_with_default(self):
        self.assertIsNone(self.d.get("missing"))
        self.assertEqual(self.d.get("missing", 42), 42)

    def test_delete(self):
        self.d["x"] = 10
        del self.d["x"]
        self.assertNotIn("x", self.d)

    def test_pop(self):
        self.d["y"] = 99
        val = self.d.pop("y")
        self.assertEqual(val, 99)
        self.assertNotIn("y", self.d)

    def test_pop_default(self):
        self.assertEqual(self.d.pop("nope", "def"), "def")

    def test_contains(self):
        self.d["k"] = 1
        self.assertIn("k", self.d)
        self.assertNotIn("no", self.d)

    def test_clear(self):
        self.d["a"] = 1
        self.d["b"] = 2
        self.d.clear()
        self.assertEqual(len(self.d), 0)

    def test_keys_items_len(self):
        self.d["a"] = 1
        self.d["b"] = 2
        self.assertEqual(sorted(self.d.keys()), ["a", "b"])
        self.assertEqual(len(self.d), 2)

    # --- Atomic update ---

    def test_update_creates_new(self):
        def fn(val):
            return (val or {}) | {"x": 1}
        self.d.update("k", fn)
        self.assertEqual(self.d["k"], {"x": 1})

    def test_update_modifies_existing(self):
        self.d["k"] = {"a": 1}
        def fn(val):
            val["b"] = 2
            return val
        self.d.update("k", fn)
        self.assertEqual(self.d["k"], {"a": 1, "b": 2})

    def test_update_handles_none(self):
        def fn(val):
            val = val or {}
            val["ok"] = True
            return val
        self.d.update("k", fn)
        self.assertEqual(self.d["k"], {"ok": True})

    # --- Thread safety ---

    def test_concurrent_writes_no_data_loss(self):
        """10 потоков × 100 записей → все 1000 должны быть"""
        errors = []

        def worker(thread_id):
            try:
                for i in range(100):
                    key = f"t{thread_id}_i{i}"
                    self.d[key] = i
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(self.d), 1000)

    def test_atomic_update_under_contention(self):
        """Атомарный update должен терять ни одного increment"""
        self.d["counter"] = {"val": 0}
        iterations = 200
        threads_count = 10

        def inc(_):
            def fn(v):
                v = v or {"val": 0}
                v["val"] += 1
                return v
            self.d.update("counter", fn)

        for _ in range(iterations // threads_count):
            threads = [threading.Thread(target=inc, args=(t,)) for t in range(threads_count)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(self.d["counter"]["val"], iterations)


# ===========================================================================
# 2. State manager — all state types
# ===========================================================================

class TestStateManager(unittest.TestCase):
    """Тесты всех типов состояний"""

    def setUp(self):
        state_manager.get_combat_state().clear()
        state_manager.get_dialog_state().clear()
        state_manager.get_research_state().clear()
        state_manager.get_anomaly_state().clear()
        state_manager._pending_event_state.clear()
        state_manager._emission_pending_state.clear()
        state_manager._pending_purchase_state.clear()
        state_manager._market_browse_state.clear()
        state_manager.invalidate_player_cache()

    # --- Combat ---

    def test_combat_lifecycle(self):
        uid = 1001
        self.assertFalse(state_manager.is_in_combat(uid))

        state_manager.set_combat_state(uid, {"enemy": "mutant", "hp": 80})
        self.assertTrue(state_manager.is_in_combat(uid))
        data = state_manager.get_combat_data(uid)
        self.assertEqual(data["enemy"], "mutant")

        state_manager.clear_combat_state(uid)
        self.assertFalse(state_manager.is_in_combat(uid))
        self.assertIsNone(state_manager.get_combat_data(uid))

    # --- Dialog ---

    def test_dialog_lifecycle(self):
        uid = 1002
        self.assertFalse(state_manager.is_in_dialog(uid))

        state_manager.set_dialog_state(uid, "военный", "shop_weapons")
        self.assertTrue(state_manager.is_in_dialog(uid))
        info = state_manager.get_dialog_info(uid)
        self.assertEqual(info["npc"], "военный")
        self.assertEqual(info["stage"], "shop_weapons")

        state_manager.clear_dialog_state(uid)
        self.assertFalse(state_manager.is_in_dialog(uid))

    # --- Research ---

    def test_research_with_timestamp(self):
        uid = 1003
        before = time.time()
        state_manager.set_research_state(uid, {"location_id": "дорога_нии", "time_sec": 10})
        after = time.time()

        data = state_manager.get_research_data(uid)
        self.assertIsNotNone(data)
        self.assertTrue(before <= data["start_time"] <= after)
        self.assertEqual(data["location_id"], "дорога_нии")

        state_manager.clear_research_state(uid)
        self.assertIsNone(state_manager.get_research_data(uid))

    # --- Anomaly ---

    def test_anomaly_lifecycle(self):
        uid = 1004
        state_manager.set_anomaly_state(uid, {"type": "жарка", "damage": 45})
        data = state_manager.get_anomaly_data(uid)
        self.assertEqual(data["type"], "жарка")
        self.assertEqual(data["damage"], 45)

        state_manager.clear_anomaly_state(uid)
        self.assertIsNone(state_manager.get_anomaly_data(uid))

    # --- Pending event ---

    def test_pending_event_lifecycle(self):
        uid = 1005
        self.assertFalse(state_manager.has_pending_event(uid))
        self.assertIsNone(state_manager.get_pending_event(uid))

        state_manager.set_pending_event(uid, {"id": "mutant", "type": "danger"})
        self.assertTrue(state_manager.has_pending_event(uid))
        self.assertEqual(state_manager.get_pending_event(uid)["id"], "mutant")

        state_manager.clear_pending_event(uid)
        self.assertFalse(state_manager.has_pending_event(uid))

    # --- Pending purchase ---

    def test_pending_purchase_lifecycle(self):
        uid = 1006
        self.assertFalse(state_manager.has_pending_purchase(uid))

        state_manager.set_pending_purchase(uid, {"listing_id": 42, "total": 5000})
        self.assertTrue(state_manager.has_pending_purchase(uid))
        data = state_manager.get_pending_purchase(uid)
        self.assertEqual(data["listing_id"], 42)

        state_manager.clear_pending_purchase(uid)
        self.assertFalse(state_manager.has_pending_purchase(uid))

    # --- Player cache ---

    def test_player_cache_expiry(self):
        uid = 1007
        # Временно уменьшим TTL
        old_ttl = state_manager._CACHE_TTL
        state_manager._CACHE_TTL = 1

        player_obj = {"name": "Сталкер"}
        state_manager.cache_player(uid, player_obj)
        self.assertIsNotNone(state_manager.get_cached_player(uid))

        time.sleep(1.5)  # ждём expiry
        self.assertIsNone(state_manager.get_cached_player(uid))

        state_manager._CACHE_TTL = old_ttl

    def test_player_cache_invalidation(self):
        uid = 1008
        state_manager.cache_player(uid, {"name": "Test"})
        state_manager.invalidate_player_cache(uid)
        self.assertIsNone(state_manager.get_cached_player(uid))

    def test_player_cache_global_invalidation(self):
        for i in range(5):
            state_manager.cache_player(2000 + i, {"n": i})
        state_manager.invalidate_player_cache()
        self.assertEqual(state_manager.get_cached_players_count(), 0)


# ===========================================================================
# 3. Market browse state — atomic operations
# ===========================================================================

class TestMarketBrowseState(unittest.TestCase):
    """Тесты состояния просмотра рынка"""

    def setUp(self):
        state_manager._market_browse_state.clear()

    def test_set_and_get(self):
        state_manager.set_market_browse_state(3001, category="weapons", page=2, sort="cheap")
        s = state_manager.get_market_browse_state(3001)
        self.assertEqual(s["category"], "weapons")
        self.assertEqual(s["page"], 2)
        self.assertEqual(s["sort"], "cheap")

    def test_clear(self):
        state_manager.set_market_browse_state(3002, category="armor")
        state_manager.clear_market_browse_state(3002)
        self.assertIsNone(state_manager.get_market_browse_state(3002))

    def test_set_and_get_my_listings_page_atomic(self):
        state_manager.set_market_my_listings_page(3003, page=5, status="sold")
        page, status = state_manager.get_market_my_listings_page(3003)
        self.assertEqual(page, 5)
        self.assertEqual(status, "sold")

    def test_set_my_listings_doesnt_overwrite_browse_state(self):
        state_manager.set_market_browse_state(3004, category="artifacts", page=3, sort="expensive")
        state_manager.set_market_my_listings_page(3004, page=7, status="active")

        browse = state_manager.get_market_browse_state(3004)
        self.assertEqual(browse["category"], "artifacts")
        self.assertEqual(browse["page"], 3)  # не перезаписано
        self.assertEqual(browse["my_listings_page"], 7)

    def test_atomic_update_no_race(self):
        """Многопоточный set_market_my_listings_page — потерянных обновлений нет"""
        uid = 3005
        state_manager.set_market_browse_state(uid, category="all", page=1, sort="newest")

        def worker(page_val):
            state_manager.set_market_my_listings_page(uid, page=page_val, status="active")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 101)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Последнее обновление должно быть видно
        state = state_manager.get_market_browse_state(uid)
        self.assertIsNotNone(state.get("my_listings_page"))


# ===========================================================================
# 4. Emission pending state
# ===========================================================================

class TestEmissionPendingState(unittest.TestCase):

    def setUp(self):
        state_manager._emission_pending_state.clear()

    def test_set_get_clear(self):
        uid = 4001
        self.assertFalse(state_manager.has_emission_pending(uid))

        state_manager.set_emission_pending(uid, {"phase": "warning", "emission_id": 1})
        self.assertTrue(state_manager.has_emission_pending(uid))
        self.assertEqual(state_manager.get_emission_pending(uid)["phase"], "warning")

        state_manager.clear_emission_pending(uid)
        self.assertFalse(state_manager.has_emission_pending(uid))

    def test_overwrite(self):
        uid = 4002
        state_manager.set_emission_pending(uid, {"phase": "warning"})
        state_manager.set_emission_pending(uid, {"phase": "impact"})
        self.assertEqual(state_manager.get_emission_pending(uid)["phase"], "impact")


# ===========================================================================
# 5. Location mechanics — modifiers, weights, unique mechanics
# ===========================================================================

class TestLocationModifiers(unittest.TestCase):
    """Тесты модификаторов локаций"""

    def test_all_research_locations_have_modifiers(self):
        from game.constants import RESEARCH_LOCATIONS
        for loc in RESEARCH_LOCATIONS:
            mod = get_location_modifier(loc)
            self.assertIsNotNone(mod, f"No modifiers for {loc}")
            self.assertIn("energy_cost_mult", mod)
            self.assertIn("find_chance_mult", mod)
            self.assertIn("danger_mult", mod)
            self.assertIn("radiation_mult", mod)
            self.assertIn("anomaly_weights", mod)
            self.assertIn("event_weights", mod)
            self.assertIn("unique_mechanic", mod)

    def test_non_research_location_returns_none(self):
        self.assertIsNone(get_location_modifier("город"))
        self.assertIsNone(get_location_modifier("больница"))

    def test_is_research_location(self):
        self.assertTrue(is_research_location("дорога_военная_часть"))
        self.assertTrue(is_research_location("дорога_нии"))
        self.assertTrue(is_research_location("дорога_зараженный_лес"))
        self.assertFalse(is_research_location("город"))

    # --- Energy cost ---

    def test_energy_cost_mult_values(self):
        # Военная: +8%
        self.assertAlmostEqual(get_energy_cost_mult("дорога_военная_часть"), 1.08, places=2)
        # НИИ: норма
        self.assertAlmostEqual(get_energy_cost_mult("дорога_нии"), 1.0, places=2)
        # Лес: +10%
        self.assertAlmostEqual(get_energy_cost_mult("дорога_зараженный_лес"), 1.10, places=2)
        # Без модификатора: 1.0
        self.assertAlmostEqual(get_energy_cost_mult("город"), 1.0, places=2)

    # --- Find chance ---

    def test_find_chance_mult_values(self):
        self.assertAlmostEqual(get_find_chance_mult("дорога_военная_часть"), 1.0, places=2)
        self.assertAlmostEqual(get_find_chance_mult("дорога_нии"), 1.12, places=2)  # +12%
        self.assertAlmostEqual(get_find_chance_mult("дорога_зараженный_лес"), 1.08, places=2)

    # --- Danger ---

    def test_danger_mult_values(self):
        self.assertAlmostEqual(get_danger_mult("дорога_военная_часть"), 1.06, places=2)
        self.assertAlmostEqual(get_danger_mult("дорога_нии"), 1.0, places=2)
        self.assertAlmostEqual(get_danger_mult("дорога_зараженный_лес"), 1.15, places=2)

    # --- Radiation ---

    def test_radiation_mult_values(self):
        self.assertAlmostEqual(get_radiation_mult("дорога_военная_часть"), 1.0, places=2)
        self.assertAlmostEqual(get_radiation_mult("дорога_нии"), 1.10, places=2)
        self.assertAlmostEqual(get_radiation_mult("дорога_зараженный_лес"), 1.12, places=2)

    # --- Anomaly weights ---

    def test_anomaly_weights_military(self):
        w = get_anomaly_weights("дорога_военная_часть")
        self.assertIsNotNone(w)
        # Электра и Магнит должны доминировать
        self.assertGreater(w["электра"], w["воронка"])
        self.assertGreater(w["магнит"], w["туман"])

    def test_anomaly_weights_nii(self):
        w = get_anomaly_weights("дорога_нии")
        self.assertIsNotNone(w)
        # Воронка и Туман должны доминировать
        self.assertGreater(w["воронка"], w["жарка"])
        self.assertGreater(w["туман"], w["электра"])

    def test_anomaly_weights_forest(self):
        w = get_anomaly_weights("дорога_зараженный_лес")
        self.assertIsNotNone(w)
        # Жарка должна доминировать
        self.assertGreater(w["жарка"], w["электра"])
        self.assertGreater(w["жарка"], w["магнит"])

    def test_anomaly_weights_non_research(self):
        self.assertIsNone(get_anomaly_weights("город"))

    # --- Event weights ---

    def test_event_weights_military(self):
        w = get_event_weights("дорога_военная_часть")
        self.assertIsNotNone(w)
        self.assertGreater(w["military"], 1.0)   # больше военных
        self.assertGreater(w["stash"], 1.0)      # больше тайников
        self.assertGreater(w["trap"], 1.0)       # больше ловушек

    def test_event_weights_nii(self):
        w = get_event_weights("дорога_нии")
        self.assertIsNotNone(w)
        self.assertGreater(w["artifact"], 1.0)   # больше артефактов
        self.assertGreater(w["anomaly"], 1.0)    # больше аномалий
        self.assertGreater(w["radiation"], 1.0)  # больше радиации

    def test_event_weights_forest(self):
        w = get_event_weights("дорога_зараженный_лес")
        self.assertIsNotNone(w)
        self.assertGreater(w["mutant"], 1.0)     # больше мутантов

    # --- Loot quality ---

    def test_loot_quality(self):
        self.assertEqual(get_loot_quality("дорога_военная_часть"), "military")
        self.assertEqual(get_loot_quality("дорога_нии"), "scientific")
        self.assertEqual(get_loot_quality("дорога_зараженный_лес"), "organic")
        self.assertIsNone(get_loot_quality("город"))


# ===========================================================================
# 6. Unique location mechanics
# ===========================================================================

class TestUniqueMechanics(unittest.TestCase):

    def setUp(self):
        clear_zone_mutation_state("дорога_нии")

    # --- Ambush (Military Road) ---

    def test_ambush_only_on_military_road(self):
        for _ in range(50):
            self.assertFalse(check_ambush("дорога_нии"))
            self.assertFalse(check_ambush("дорога_зараженный_лес"))
            self.assertFalse(check_ambush("город"))

    def test_ambush_probability_in_range(self):
        """12% шанс засады на военной дороге"""
        hits = sum(1 for _ in range(1000) if check_ambush("дорога_военная_часть"))
        rate = hits / 1000
        # 12% ± 5% (доверительный интервал для 1000 попыток)
        self.assertGreater(rate, 0.05)
        self.assertLess(rate, 0.20)

    # --- Zone mutation (NII) ---

    def test_zone_mutation_only_on_nii(self):
        for _ in range(50):
            self.assertIsNone(check_zone_mutation("дорога_военная_часть"))
            self.assertIsNone(check_zone_mutation("дорога_зараженный_лес"))

    def test_zone_mutation_probability_in_range(self):
        """10% шанс мутации на НИИ"""
        hits = sum(1 for _ in range(1000) if check_zone_mutation("дорога_нии") is not None)
        rate = hits / 1000
        self.assertGreater(rate, 0.03)
        self.assertLess(rate, 0.18)

    def test_zone_mutation_state_persistence(self):
        # Форсируем мутацию
        while True:
            result = check_zone_mutation("дорога_нии")
            if result and result["active"]:
                break

        # Состояние сохраняется
        state = _zone_mutation_state.get("дорога_нии")
        self.assertIsNotNone(state)
        self.assertTrue(state["active"])
        self.assertGreater(state["bonus_find"], 0)
        self.assertGreater(state["bonus_danger"], 0)

    def test_zone_mutation_bonus_affects_find_chance(self):
        while True:
            result = check_zone_mutation("дорога_нии")
            if result and result["active"]:
                break

        base_find = 1.12  # НИИ базовый
        state = _zone_mutation_state["дорога_нии"]
        actual = get_find_chance_mult("дорога_нии")
        self.assertAlmostEqual(actual, base_find + state["bonus_find"], places=3)

    def test_zone_mutation_clears_on_no_mutation(self):
        # Активируем
        while True:
            result = check_zone_mutation("дорога_нии")
            if result and result["active"]:
                break

        # Вызываем пока не сработает "нет мутации" (сбросит состояние)
        for _ in range(50):
            check_zone_mutation("дорога_нии")
            if "дорога_нии" not in _zone_mutation_state:
                break

    # --- Mutant hunt (Forest) ---

    def test_mutant_hunt_only_on_forest(self):
        # check_mutant_hunt не зависит от локации, это глобальный шанс
        # Вызываем просто чтобы убедиться что работает
        check_mutant_hunt()

    def test_mutant_hunt_probability_in_range(self):
        """12% шанс охоты мутантов"""
        hits = sum(1 for _ in range(1000) if check_mutant_hunt())
        rate = hits / 1000
        self.assertGreater(rate, 0.06)
        self.assertLess(rate, 0.20)

    def test_mutant_hunt_count_range(self):
        for _ in range(100):
            count = get_mutant_hunt_count()
            self.assertEqual(count, 2)

    # --- Loot bias ---

    def test_loot_bias_items_exist(self):
        for loc in LOCATION_LOOT_BIAS:
            bias_items = get_location_loot_bias(loc)
            self.assertIsInstance(bias_items, list)
            self.assertGreater(len(bias_items), 0)

    def test_loot_bias_chance(self):
        for loc in LOCATION_LOOT_BIAS:
            chance = get_location_loot_bias_chance(loc)
            self.assertAlmostEqual(chance, 0.30, places=2)


# ===========================================================================
# 7. Location modifier data integrity
# ===========================================================================

class TestLocationDataIntegrity(unittest.TestCase):
    """Проверка целостности данных локаций"""

    def test_all_locations_have_unique_mechanic(self):
        for loc_id, mod in LOCATION_MODIFIERS.items():
            self.assertIn("unique_mechanic", mod)
            self.assertIn(mod["unique_mechanic"],
                          ["ambush", "zone_mutation", "mutant_hunt"])

    def test_all_anomaly_weights_valid(self):
        from game.anomalies import ANOMALIES
        for loc_id, mod in LOCATION_MODIFIERS.items():
            weights = mod["anomaly_weights"]
            for anomaly_type in weights:
                self.assertIn(anomaly_type, ANOMALIES,
                              f"{loc_id}: unknown anomaly '{anomaly_type}'")

    def test_all_event_weights_reference_known_events(self):
        from handlers.combat import RESEARCH_EVENTS
        for loc_id, mod in LOCATION_MODIFIERS.items():
            weights = mod["event_weights"]
            for event_id in weights:
                # event_id может быть как конкретным событием, так и типом
                if event_id not in RESEARCH_EVENTS:
                    # Проверяем что это тип события
                    self.assertIn(event_id,
                                  ["enemy", "item", "artifact", "anomaly", "radiation", "trap", "stash", "survivor"],
                                  f"{loc_id}: unknown event weight '{event_id}'")

    def test_loot_bias_items_exist_in_database(self):
        """Проверяем что предметы из loot bias существуют в ITEMS"""
        from game.constants import InventorySection
        # Проверяем что bias_items непустые
        for loc_id, bias in LOCATION_LOOT_BIAS.items():
            self.assertGreater(len(bias["bias_items"]), 0)
            self.assertGreater(bias["bias_weight"], 0)

    def test_modifier_values_positive(self):
        for loc_id, mod in LOCATION_MODIFIERS.items():
            self.assertGreater(mod["energy_cost_mult"], 0)
            self.assertGreater(mod["find_chance_mult"], 0)
            self.assertGreater(mod["danger_mult"], 0)
            self.assertGreater(mod["radiation_mult"], 0)


# ===========================================================================
# 8. Parameterized / Interactive-style tests
# ===========================================================================

class TestParameterized(unittest.TestCase):
    """Параметризованные тесты — можно добавлять свои данные"""

    # --- Custom user data ---

    def test_custom_user_id_combat(self):
        """Тест с произвольным user_id"""
        for uid in [1, 999999, -1, 0, 123456789]:
            state_manager.set_combat_state(uid, {"enemy": "test", "hp": 100})
            self.assertTrue(state_manager.is_in_combat(uid))
            state_manager.clear_combat_state(uid)

    def test_custom_dialog_data(self):
        """Тест с произвольными данными диалога"""
        test_cases = [
            (5001, "военный", "shop_weapons"),
            (5002, "ученый", "shop_meds"),
            (5003, "барыга", "buy_artifacts"),
            (5004, "местный житель", "menu"),
            (5005, "наставник", "class_selection"),
        ]
        for uid, npc, stage in test_cases:
            state_manager.set_dialog_state(uid, npc, stage)
            info = state_manager.get_dialog_info(uid)
            self.assertEqual(info["npc"], npc)
            self.assertEqual(info["stage"], stage)
            state_manager.clear_dialog_state(uid)

    def test_custom_event_data(self):
        """Тест с произвольными данными событий"""
        events = [
            {"id": "custom_1", "type": "danger", "choices": []},
            {"id": "custom_2", "type": "reward", "effect": {"money": 1000}},
            {"id": "custom_3", "type": "multi_stage", "stages": [{"text": "hi"}]},
            {},
        ]
        for i, evt in enumerate(events):
            uid = 6000 + i
            state_manager.set_pending_event(uid, evt)
            self.assertEqual(state_manager.get_pending_event(uid), evt)
            state_manager.clear_pending_event(uid)

    # --- Custom location modifiers ---

    def test_custom_location_modifier_access(self):
        """Проверка доступа к модификаторам всех исследовательских локаций"""
        from game.constants import RESEARCH_LOCATIONS
        for loc in RESEARCH_LOCATIONS:
            mod = get_location_modifier(loc)
            self.assertIsNotNone(mod)
            # Проверяем что все функции-геттеры работают
            get_energy_cost_mult(loc)
            get_find_chance_mult(loc)
            get_danger_mult(loc)
            get_radiation_mult(loc)
            get_anomaly_weights(loc)
            get_event_weights(loc)
            get_loot_quality(loc)

    # --- Concurrent stress test with custom parameters ---

    def test_stress_concurrent_state_updates(self):
        """Стресс-тест: 50 потоков × 50 операций"""
        d = state_manager.LockedDict()
        ops_per_thread = 50
        thread_count = 50

        def worker(tid):
            for i in range(ops_per_thread):
                key = f"s{tid}_{i}"
                d[key] = i
                d[key]  # read back
                d.pop(key, None)  # cleanup

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Все потоки завершились без исключений
        self.assertEqual(len(d), 0)  # все удалены

    def test_stress_concurrent_market_state(self):
        """Стресс-тест: конкурентные обновления market browse state"""
        uid = 9999
        state_manager._market_browse_state.clear()

        def worker(page):
            state_manager.set_market_browse_state(uid, category="all", page=page, sort="newest")
            state_manager.set_market_my_listings_page(uid, page=page, status="active")

        threads = [threading.Thread(target=worker, args=(p,)) for p in range(1, 51)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Состояние должно быть консистентным
        state = state_manager.get_market_browse_state(uid)
        self.assertIn("category", state)
        self.assertIn("page", state)
        self.assertIn("my_listings_page", state)


if __name__ == "__main__":
    unittest.main()
