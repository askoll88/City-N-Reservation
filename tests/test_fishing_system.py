import random
import time
import unittest
from unittest.mock import patch

from game.fishing import (
    FISHING_DURATION_SECONDS,
    FISH_LOCKER_CAPACITY,
    FISH_SPECIES,
    FALLBACK_GEAR,
    GEAR,
    LAKE_LOCATION,
    LUCHIK_PROTECTED_UPGRADE_ITEMS,
    LUCHIK_ROD_UPGRADES,
    SPOTS,
    _roll_fish_entry,
    _gear_gap_for_fish,
    _resolve_fight_action,
    _select_gear,
    _start_fishing_fight,
    check_fishing,
    complete_luchik_order,
    cook_recipe,
    buy_luchik_shop_item,
    handle_fishing_fight_action,
    sell_luchik_fish,
    show_fish_locker,
    start_fishing,
)
from game.map_schema import get_map_location


class DummyMessages:
    def __init__(self):
        self.sent = []

    def send(self, **kwargs):
        self.sent.append(kwargs)
        return 1


class DummyVk:
    def __init__(self):
        self.messages = DummyMessages()


class DummyPlayer:
    user_id = 777
    current_location_id = LAKE_LOCATION
    level = 28
    energy = 50
    max_energy = 100
    health = 100
    max_health = 100
    radiation = 0
    perception = 5
    luck = 5

    def add_experience(self, amount):
        return amount

    def buy_item(self, item_name):
        self.money -= 10
        return True, f"Ты купил {item_name}"


class FishingSystemTest(unittest.TestCase):
    def test_lake_is_midgame_fishing_location(self):
        tourbase = get_map_location("турбаза_лучик")
        lake = get_map_location("озеро")

        self.assertEqual(tourbase["type"], "safehouse")
        self.assertEqual(tourbase["level_min"], 24)
        self.assertEqual(lake["type"], "resource_job")
        self.assertEqual(lake["loot_profile"], "lake_fishing")

    def test_start_fishing_spends_energy_and_stores_state(self):
        player = DummyPlayer()
        vk = DummyVk()
        spot = SPOTS["deep"]

        with patch("game.fishing.service.database.get_runtime_state", return_value=None), \
             patch("game.fishing.service.database.get_inventory_item_quantities", return_value={}), \
             patch("game.fishing.service.database.set_runtime_state") as set_state, \
             patch("game.fishing.service.database.remove_item_from_inventory") as remove_item, \
             patch("game.fishing.service.database.update_user_stats") as update_stats:
            handled = start_fishing(player, vk, 777, "deep")

        self.assertTrue(handled)
        self.assertEqual(player.energy, 50 - spot.energy_cost)
        update_stats.assert_called_once_with(777, energy=player.energy)
        self.assertEqual(set_state.call_args.args[2]["spot"], "deep")
        self.assertEqual(set_state.call_args.args[2]["gear_label"], "Леска с крючком")
        self.assertEqual(set_state.call_args.args[2]["early_checks"], 0)
        self.assertEqual(set_state.call_args.args[2]["last_check_at"], 0)
        remove_item.assert_not_called()
        self.assertIn("Глубокий заброс", vk.messages.sent[-1]["message"])

    def test_start_fishing_uses_best_gear_and_consumes_bait(self):
        player = DummyPlayer()
        vk = DummyVk()

        with patch("game.fishing.service.database.get_runtime_state", return_value=None), \
             patch("game.fishing.service.database.get_inventory_item_quantities", side_effect=[
                 {"Старая удочка": 1},
                 {"Черви": 3},
             ]), \
             patch("game.fishing.service.database.set_runtime_state") as set_state, \
             patch("game.fishing.service.database.remove_item_from_inventory") as remove_item, \
             patch("game.fishing.service.database.update_user_stats"):
            handled = start_fishing(player, vk, 777, "shore")

        self.assertTrue(handled)
        state = set_state.call_args.args[2]
        self.assertEqual(state["gear"], "Старая удочка")
        self.assertEqual(state["bait"], "Черви")
        remove_item.assert_called_once_with(777, "Черви", 1)
        self.assertIn("Старая удочка", vk.messages.sent[-1]["message"])

    def test_start_fishing_drops_bait_bonus_when_consume_fails(self):
        player = DummyPlayer()
        vk = DummyVk()

        with patch("game.fishing.service.database.get_runtime_state", return_value=None), \
             patch("game.fishing.service.database.get_inventory_item_quantities", side_effect=[
                 {},
                 {"Черви": 1},
             ]), \
             patch("game.fishing.service.database.set_runtime_state") as set_state, \
             patch("game.fishing.service.database.remove_item_from_inventory", return_value=False), \
             patch("game.fishing.service.database.update_user_stats"):
            handled = start_fishing(player, vk, 777, "shore")

        self.assertTrue(handled)
        state = set_state.call_args.args[2]
        self.assertEqual(state["bait"], "")
        self.assertIn("без наживки", vk.messages.sent[-1]["message"])

    def test_select_gear_falls_back_without_rod(self):
        with patch("game.fishing.service.database.get_inventory_item_quantities", return_value={}):
            gear = _select_gear(777)

        self.assertEqual(gear.label, "Леска с крючком")

    def test_check_fishing_grants_catch_after_timer(self):
        player = DummyPlayer()
        vk = DummyVk()
        state = {
            "started_at": int(time.time()) - FISHING_DURATION_SECONDS - 1,
            "duration": FISHING_DURATION_SECONDS,
            "spot": "shore",
            "gear": "Старая удочка",
            "bait": "Черви",
            "seed": 12345,
        }

        with patch("game.fishing.service.database.get_runtime_state", return_value=state), \
             patch("game.fishing.service._should_start_fight", return_value=False), \
             patch("game.fishing.service.database.add_item_to_inventory", return_value=True) as add_item, \
             patch("game.fishing.service.database.add_fish_to_locker_transaction", return_value={"success": True}) as add_fish, \
             patch("game.fishing.service.database.clear_runtime_state") as clear_state, \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = check_fishing(player, vk, 777)

        self.assertTrue(handled)
        self.assertFalse(add_item.called)
        self.assertTrue(add_fish.called)
        clear_state.assert_called_once_with(777, "fishing_state")
        self.assertIn("Рыбалка завершена", vk.messages.sent[-1]["message"])

    def test_check_fishing_starts_fight_on_early_bite_roll(self):
        player = DummyPlayer()
        vk = DummyVk()
        now = int(time.time())
        state = {
            "started_at": now - 60,
            "duration": FISHING_DURATION_SECONDS,
            "early_checks": 0,
            "last_check_at": 0,
            "spot": "shore",
            "gear": "Старая удочка",
            "bait": "Черви",
            "seed": 12345,
        }

        with patch("game.fishing.service.database.get_runtime_state", return_value=state), \
             patch("game.fishing.service._roll_early_bite", return_value=(True, 42)) as roll_bite, \
             patch("game.fishing.service.database.set_runtime_state") as set_state, \
             patch("game.fishing.service.database.add_item_to_inventory", return_value=True) as add_item, \
             patch("game.fishing.service.database.add_fish_to_locker_transaction", return_value={"success": True}) as add_fish, \
             patch("game.fishing.service.database.clear_runtime_state") as clear_state:
            handled = check_fishing(player, vk, 777)

        self.assertTrue(handled)
        roll_bite.assert_called_once()
        self.assertEqual(set_state.call_args.args[2]["mode"], "fight")
        self.assertFalse(add_item.called)
        self.assertFalse(add_fish.called)
        clear_state.assert_not_called()
        self.assertIn("Резкая поклёвка", vk.messages.sent[-1]["message"])

    def test_fishing_fight_action_finishes_with_adjusted_fish(self):
        player = DummyPlayer()
        vk = DummyVk()
        state = {
            "mode": "fight",
            "fish_entry": {
                "name": "Тяжелый карп",
                "tier": "uncommon",
                "weight_kg": 2.0,
                "price_per_kg": 100,
                "value": 200,
                "spot": "deep",
                "caught_at": int(time.time()),
            },
            "xp_gain": 100,
            "tier": "uncommon",
            "hazard": False,
            "spot": "deep",
            "gear": "Старая удочка",
            "gear_label": "Старая удочка",
            "bait": "",
            "bait_label": "",
            "bonus_rewards": [],
            "seed": 12345,
            "turn": 0,
            "turns_left": 1,
            "control": 70,
            "quality_pct": 100,
            "signal": "tremble",
        }

        with patch("game.fishing.service.database.get_runtime_state", return_value=state), \
             patch("game.fishing.service.database.add_item_to_inventory", return_value=True), \
             patch("game.fishing.service.database.add_fish_to_locker_transaction", return_value={"success": True}) as add_fish, \
             patch("game.fishing.service.database.clear_runtime_state") as clear_state, \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = handle_fishing_fight_action(player, vk, 777, "Вываживать")

        self.assertTrue(handled)
        fish_entry = add_fish.call_args.args[1]
        self.assertIn("fight_quality", fish_entry)
        self.assertGreaterEqual(fish_entry["fight_quality"], 65)
        self.assertLessEqual(fish_entry["fight_quality"], 125)
        clear_state.assert_called_once_with(777, "fishing_state")
        self.assertIn("Вываживание", vk.messages.sent[-1]["message"])

    def test_fishing_fight_actions_are_risk_based_not_fixed_answers(self):
        player = DummyPlayer()
        gear = next(row for row in GEAR if row.name == "Старая удочка")
        base_state = {
            "seed": 12345,
            "turn": 0,
            "control": 70,
            "quality_pct": 100,
        }

        pull = _resolve_fight_action(player, dict(base_state), "pull", "tremble", gear)
        release = _resolve_fight_action(player, dict(base_state), "release", "jerk", gear)

        self.assertGreaterEqual(pull["risk"], 5)
        self.assertLessEqual(pull["risk"], 85)
        self.assertGreaterEqual(release["risk"], 5)
        self.assertLessEqual(release["risk"], 85)
        self.assertNotEqual(pull["risk"], release["risk"])

    def test_risky_surge_is_progress_not_one_click_finish(self):
        player = DummyPlayer()
        state = {
            "seed": 12345,
            "turn": 0,
            "control": 61,
            "quality_pct": 100,
        }

        surge = _resolve_fight_action(player, state, "surge", "tremble", FALLBACK_GEAR)

        self.assertEqual(surge["progress"], 2)
        self.assertGreaterEqual(surge["risk"], 25)
        self.assertLessEqual(surge["quality"], 115)

    def test_heavy_anomaly_fish_overloads_basic_line(self):
        fish_entry = {
            "name": "Аномальный голавль",
            "tier": "rare",
            "weight_kg": 4.57,
            "spot": "anomaly",
        }

        self.assertGreaterEqual(_gear_gap_for_fish(FALLBACK_GEAR, fish_entry), 4)

    def test_weak_gear_cannot_start_oversized_anomaly_fish_fight(self):
        player = DummyPlayer()
        vk = DummyVk()
        state = {
            "spot": "anomaly",
        }
        fish_entry = {
            "name": "Аномальный голавль",
            "tier": "rare",
            "weight_kg": 4.57,
            "price_per_kg": 500,
            "value": 2285,
            "spot": "anomaly",
            "caught_at": int(time.time()),
        }

        with patch("game.fishing.service.database.add_fish_to_locker_transaction") as add_fish, \
             patch("game.fishing.service.database.clear_runtime_state") as clear_state, \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = _start_fishing_fight(
                player, vk, 777, state, fish_entry, 180, "rare", False, [], FALLBACK_GEAR, None, 12345, True
            )

        self.assertTrue(handled)
        add_fish.assert_not_called()
        clear_state.assert_called_once_with(777, "fishing_state")
        self.assertIn("Рыба сорвалась", vk.messages.sent[-1]["message"])

    def test_check_fishing_reports_missed_early_bite_roll(self):
        player = DummyPlayer()
        vk = DummyVk()
        now = int(time.time())
        state = {
            "started_at": now - 60,
            "duration": FISHING_DURATION_SECONDS,
            "early_checks": 2,
            "last_check_at": 0,
            "spot": "shore",
            "gear": "Старая удочка",
            "bait": "Черви",
            "seed": 12345,
        }

        with patch("game.fishing.service.database.get_runtime_state", return_value=state), \
             patch("game.fishing.service._roll_early_bite", return_value=(False, 37)) as roll_bite, \
             patch("game.fishing.service.database.set_runtime_state") as set_state, \
             patch("game.fishing.service.database.add_item_to_inventory") as add_item, \
             patch("game.fishing.service.database.add_fish_to_locker_transaction") as add_fish, \
             patch("game.fishing.service.database.clear_runtime_state") as clear_state:
            handled = check_fishing(player, vk, 777)

        self.assertTrue(handled)
        roll_bite.assert_called_once()
        self.assertEqual(set_state.call_args.args[2]["early_checks"], 3)
        add_item.assert_not_called()
        add_fish.assert_not_called()
        clear_state.assert_not_called()
        self.assertIn("Поплавок пока молчит", vk.messages.sent[-1]["message"])
        self.assertIn("37%", vk.messages.sent[-1]["message"])

    def test_fish_entry_has_weight_and_value_in_range(self):
        fish = next(row for row in FISH_SPECIES if row.name == "Тяжелый карп")
        entry = _roll_fish_entry(fish, SPOTS["deep"], random.Random(7))

        self.assertGreaterEqual(entry["weight_kg"], fish.weight_min)
        self.assertLessEqual(entry["weight_kg"], fish.weight_max)
        self.assertGreaterEqual(entry["price_per_kg"], fish.price_per_kg_min)
        self.assertLessEqual(entry["price_per_kg"], fish.price_per_kg_max)
        self.assertEqual(entry["value"], int(round(entry["weight_kg"] * entry["price_per_kg"])))

    def test_fish_pool_is_large_unique_and_weighted(self):
        names = [fish.name for fish in FISH_SPECIES]

        self.assertGreaterEqual(len(FISH_SPECIES), 200)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue({"common", "uncommon", "rare"}.issubset({fish.tier for fish in FISH_SPECIES}))
        for fish in FISH_SPECIES:
            self.assertLess(fish.weight_min, fish.weight_max, fish.name)
            self.assertLess(fish.price_per_kg_min, fish.price_per_kg_max, fish.name)
            self.assertTrue(fish.spots, fish.name)

        self.assertNotIn("Малая окунь", names)
        self.assertIn("Малый окунь", names)
        self.assertNotIn("Аномальная карась", names)
        self.assertIn("Аномальный карась", names)

    def test_luchik_sells_weighted_fish_locker(self):
        player = DummyPlayer()
        player.money = 100
        vk = DummyVk()
        locker_sale = {
            "success": True,
            "sold": [{"name": "Тяжелый карп", "weight_kg": 3.25, "value": 520}],
            "total": 520,
            "remaining_money": 620,
        }

        with patch("game.fishing.service.database.sell_fish_locker_transaction", return_value=locker_sale) as sell_locker, \
             patch("game.fishing.service.database.sell_luchik_fish_transaction", return_value={"success": False, "total": 0}), \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = sell_luchik_fish(player, vk, 777, "лучик")

        self.assertTrue(handled)
        sell_locker.assert_called_once_with(777)
        self.assertTrue(getattr(player, "_luchik_last_sale_success", False))
        self.assertEqual(player.money, 620)
        self.assertIn("3.25 кг", vk.messages.sent[-1]["message"])

    def test_luchik_does_not_track_sale_when_locker_is_empty(self):
        player = DummyPlayer()
        vk = DummyVk()

        with patch("game.fishing.service.database.sell_fish_locker_transaction", return_value={"success": False, "total": 0, "message": "В рыбном шкафу нет рыбы."}), \
             patch("game.fishing.service.database.sell_luchik_fish_transaction", return_value={"success": False, "total": 0, "message": "У тебя нет рыбы, которую берёт Лучик."}):
            handled = sell_luchik_fish(player, vk, 777, "лучик")

        self.assertTrue(handled)
        self.assertFalse(getattr(player, "_luchik_last_sale_success", False))
        self.assertIn("рыбы", vk.messages.sent[-1]["message"])

    def test_cooking_consumes_fish_from_tourbase_locker(self):
        player = DummyPlayer()
        player.current_location_id = "турбаза_лучик"
        vk = DummyVk()
        consumed = [
            {"name": "Серебристая плотва", "weight_kg": 0.4, "value": 28},
            {"name": "Пятнистый окунь", "weight_kg": 0.6, "value": 51},
        ]

        with patch("game.fishing.service.database.consume_fish_locker_entries_transaction", return_value={"success": True, "used_text": "Серебристая плотва x1, Пятнистый окунь x1", "consumed": consumed}) as consume, \
             patch("game.fishing.service.database.cook_luchik_recipe_transaction", return_value={"success": True, "message": "Готово: Уха у Лучика x1. Списано: Чистая вода x1"}), \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = cook_recipe(player, vk, 777, "уха")

        self.assertTrue(handled)
        consume.assert_called_once()
        self.assertIn("Из рыбного шкафа", vk.messages.sent[-1]["message"])

    def test_cooking_consumes_cheapest_matching_fish_from_locker(self):
        player = DummyPlayer()
        player.current_location_id = "турбаза_лучик"
        vk = DummyVk()
        consumed = [
            {"name": "Пятнистый окунь", "weight_kg": 0.6, "value": 40},
            {"name": "Старый карась", "weight_kg": 0.7, "value": 50},
        ]

        with patch("game.fishing.service.database.consume_fish_locker_entries_transaction", return_value={"success": True, "used_text": "Пятнистый окунь x1, Старый карась x1", "consumed": consumed}) as consume, \
             patch("game.fishing.service.database.cook_luchik_recipe_transaction", return_value={"success": True, "message": "Готово"}), \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = cook_recipe(player, vk, 777, "уха")

        self.assertTrue(handled)
        self.assertEqual(consume.call_args.args[2], 2)

    def test_luchik_order_consumes_fish_from_tourbase_locker(self):
        player = DummyPlayer()
        player.current_location_id = "турбаза_лучик"
        vk = DummyVk()
        consumed = [
            {"name": "Серебристая плотва", "weight_kg": 0.4, "value": 28},
            {"name": "Пятнистый окунь", "weight_kg": 0.6, "value": 51},
            {"name": "Старый карась", "weight_kg": 0.9, "value": 72},
        ]

        with patch("game.fishing.service.database.consume_fish_locker_entries_transaction", return_value={"success": True, "used_text": "Серебристая плотва x1, Пятнистый окунь x1, Старый карась x1", "consumed": consumed}), \
             patch("game.fishing.service.database.complete_luchik_order_transaction", return_value={"success": True, "message": "Заказ закрыт: Уха на вечер.\nСписано: ничего.\nНаграда: 340 руб.\nДенег сейчас: 500 руб."}), \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = complete_luchik_order(player, vk, 777, "common_fish")

        self.assertTrue(handled)
        self.assertIn("Списано из рыбного шкафа", vk.messages.sent[-1]["message"])

    def test_full_fish_locker_does_not_drop_existing_entries(self):
        player = DummyPlayer()
        vk = DummyVk()
        state = {
            "started_at": int(time.time()) - FISHING_DURATION_SECONDS - 1,
            "duration": FISHING_DURATION_SECONDS,
            "spot": "shore",
            "gear": "Старая удочка",
            "bait": "",
            "seed": 12345,
        }
        with patch("game.fishing.service.database.get_runtime_state", return_value=state), \
             patch("game.fishing.service._should_start_fight", return_value=False), \
             patch("game.fishing.service.database.add_item_to_inventory", return_value=True), \
             patch("game.fishing.service.database.add_fish_to_locker_transaction", return_value={"success": False, "full": True}), \
             patch("game.fishing.service.database.clear_runtime_state"), \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = check_fishing(player, vk, 777)

        self.assertTrue(handled)
        self.assertIn("шкаф турбазы заполнен", vk.messages.sent[-1]["message"])

    def test_show_fish_locker_lists_value_and_capacity(self):
        player = DummyPlayer()
        vk = DummyVk()
        entries = [{"name": "Тяжелый карп", "weight_kg": 3.25, "value": 520}]

        with patch("game.fishing.service.database.get_user_fish_locker", return_value=entries):
            handled = show_fish_locker(player, vk, 777)

        self.assertTrue(handled)
        message = vk.messages.sent[-1]["message"]
        self.assertIn(f"1/{FISH_LOCKER_CAPACITY}", message)
        self.assertIn("520 руб", message)

    def test_luchik_shop_buy_allows_fishing_items(self):
        player = DummyPlayer()
        player.current_location_id = "турбаза_лучик"
        player.money = 100
        vk = DummyVk()

        with patch("game.fishing.service.invalidate_player_cache"):
            handled = buy_luchik_shop_item(player, vk, 777, "2 черви")

        self.assertTrue(handled)
        self.assertEqual(player.money, 80)
        self.assertIn("Черви x2", vk.messages.sent[-1]["message"])

    def test_luchik_rod_upgrade_requires_previous_rod(self):
        player = DummyPlayer()
        player.current_location_id = "турбаза_лучик"
        player.money = 100000
        vk = DummyVk()

        with patch("game.fishing.service.database.get_inventory_item_quantities", return_value={}), \
             patch("game.fishing.service.database.remove_item_from_inventory") as remove_item:
            handled = buy_luchik_shop_item(player, vk, 777, "складная удочка")

        self.assertTrue(handled)
        remove_item.assert_not_called()
        self.assertIn("Не хватает для апгрейда", vk.messages.sent[-1]["message"])
        self.assertIn("Старая удочка", vk.messages.sent[-1]["message"])

    def test_luchik_rod_upgrade_consumes_components(self):
        player = DummyPlayer()
        player.current_location_id = "турбаза_лучик"
        player.money = 100000
        vk = DummyVk()

        with patch("game.fishing.service.database.get_inventory_item_quantities", return_value={"Старая удочка": 1}), \
             patch("game.fishing.service.database.remove_item_from_inventory", return_value=True) as remove_item, \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = buy_luchik_shop_item(player, vk, 777, "складная удочка")

        self.assertTrue(handled)
        remove_item.assert_called_once_with(777, "Старая удочка", 1)
        self.assertIn("Списано для апгрейда", vk.messages.sent[-1]["message"])

    def test_luchik_top_rod_has_long_term_requirements(self):
        requirements = dict(LUCHIK_ROD_UPGRADES["Резонансная удочка"]["requires"])

        self.assertEqual(requirements["Изолированная удочка"], 1)
        self.assertGreaterEqual(requirements["Аномальная чешуя"], 8)
        self.assertGreaterEqual(requirements["Затонувший контейнер"], 3)

    def test_luchik_upgrade_materials_require_sell_confirmation(self):
        self.assertIn("Аномальная чешуя", LUCHIK_PROTECTED_UPGRADE_ITEMS)
        self.assertIn("Затонувший контейнер", LUCHIK_PROTECTED_UPGRADE_ITEMS)
        self.assertIn("Старая удочка", LUCHIK_PROTECTED_UPGRADE_ITEMS)
        self.assertIn("Резонансная удочка", LUCHIK_PROTECTED_UPGRADE_ITEMS)


if __name__ == "__main__":
    unittest.main()
