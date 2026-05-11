import json
import random
import unittest
from unittest.mock import patch

from handlers.combat import (
    ANOMALY_GUARANTEE_FLAG,
    ANOMALY_GUARANTEE_RESEARCHES,
    _apply_weapon_damage_bonus,
    _create_early_detection_keyboard,
    _early_enemy_state,
    _hide_lower_keyboard_for_combat,
    _roll_initiative,
    _select_research_event_by_chance,
    _spawn_item,
    _will_continue_mutant_hunt,
    cancel_research,
    create_anomaly_keyboard,
    create_combat_keyboard,
    create_combat_inventory_keyboard,
    create_skills_keyboard,
    handle_early_enemy_callback,
    handle_combat_shell_decoy,
    handle_explore_time,
    RESEARCH_EVENTS,
)
from infra.state_manager import (
    clear_combat_state,
    clear_research_state,
    invalidate_edit_targets,
    is_in_combat,
    is_researching,
    set_combat_state,
    set_ui_message,
)


class DummyClassPlayer:
    player_class = "sniper"
    energy = 100


class CombatCallbackKeyboardTests(unittest.TestCase):
    def setUp(self):
        clear_combat_state(1)

    def tearDown(self):
        clear_combat_state(1)
        clear_combat_state(77)
        cancel_research(88)
        clear_research_state(88)
        invalidate_edit_targets(77)

    def test_combat_attack_button_is_callback(self):
        keyboard = json.loads(create_combat_keyboard(DummyClassPlayer(), user_id=1).get_keyboard())
        button = keyboard["buttons"][0][0]
        payload = json.loads(button["action"]["payload"])

        self.assertTrue(keyboard["inline"])
        self.assertEqual(button["action"]["type"], "callback")
        self.assertEqual(payload, {"command": "combat_action", "action": "attack"})

    def test_combat_buttons_include_current_combat_id_when_available(self):
        set_combat_state(1, {"combat_id": "fight-1"})

        keyboard = json.loads(create_combat_keyboard(DummyClassPlayer(), user_id=1).get_keyboard())
        payload = json.loads(keyboard["buttons"][0][0]["action"]["payload"])

        self.assertEqual(payload["combat_id"], "fight-1")

    def test_hide_lower_keyboard_sends_empty_regular_keyboard(self):
        class Messages:
            def __init__(self):
                self.sent = []

            def send(self, **kwargs):
                self.sent.append(kwargs)
                return 1

        class Vk:
            def __init__(self):
                self.messages = Messages()

        vk = Vk()

        _hide_lower_keyboard_for_combat(vk, 1)

        sent = vk.messages.sent[0]
        keyboard = json.loads(sent["keyboard"])
        self.assertFalse(keyboard["inline"])
        self.assertEqual(keyboard["buttons"], [])

    def test_early_detection_keyboard_offers_attack_or_flee(self):
        keyboard = json.loads(_create_early_detection_keyboard("contact-1").get_keyboard())
        payloads = [json.loads(button["action"]["payload"]) for button in keyboard["buttons"][0]]

        self.assertTrue(keyboard["inline"])
        self.assertEqual(payloads[0], {"command": "early_enemy", "action": "attack", "pending_id": "contact-1"})
        self.assertEqual(payloads[1], {"command": "early_enemy", "action": "flee", "pending_id": "contact-1"})

    def test_early_detection_attack_adds_initiative_bonus_without_guarantee(self):
        class Player:
            effective_perception = 1
            effective_luck = 1

        with patch("handlers.combat.random.randint", side_effect=[1, 20]):
            initiative = _roll_initiative(Player(), enemy_speed=10, player_bonus=4)

        self.assertEqual(initiative["player_bonus"], 4)
        self.assertFalse(initiative["player_first"])

    def test_early_detection_flee_does_not_start_combat(self):
        class Messages:
            def __init__(self):
                self.sent = []

            def send(self, **kwargs):
                self.sent.append(kwargs)
                return 1

        class Vk:
            def __init__(self):
                self.messages = Messages()

        class Player:
            current_location_id = "дорога_военная_часть"

        _early_enemy_state[77] = {
            "pending_id": "contact-1",
            "created_at": 1_000_000_000,
            "enemy": {"enemy_name": "Бандит"},
            "detection": {"chance": 1 / 30},
        }

        with patch("handlers.combat.time.time", return_value=1_000_000_001):
            handled = handle_early_enemy_callback(
                Player(),
                Vk(),
                77,
                {"command": "early_enemy", "action": "flee", "pending_id": "contact-1"},
            )

        self.assertTrue(handled)
        self.assertNotIn(77, _early_enemy_state)
        self.assertFalse(is_in_combat(77))

    def test_mutant_hunt_continuation_only_inside_forest_chain(self):
        self.assertTrue(_will_continue_mutant_hunt({"mutant_hunt": 1, "location_id": "зараженный_лес"}))
        self.assertFalse(_will_continue_mutant_hunt({"mutant_hunt": 0, "location_id": "зараженный_лес"}))
        self.assertFalse(_will_continue_mutant_hunt({"mutant_hunt": 1, "location_id": "город"}))

    def test_research_item_events_are_not_drowned_by_combat_events(self):
        random.seed(7)
        with patch("game.limited_events.get_active_limited_event", return_value=None):
            events = [
                _select_research_event_by_chance(45, 1.0, 1.0, "дорога_зараженный_лес", None)
                for _ in range(5000)
            ]

        item_events = sum(1 for event in events if RESEARCH_EVENTS.get(event, {}).get("type") == "item")
        self.assertGreater(item_events / len(events), 0.12)

    def test_research_anomaly_guarantee_is_not_far_beyond_onboarding(self):
        self.assertLessEqual(ANOMALY_GUARANTEE_RESEARCHES, 40)

    def test_research_anomaly_guarantee_forces_anomaly_and_resets_streak(self):
        with patch("handlers.combat.database.get_user_flag", return_value=ANOMALY_GUARANTEE_RESEARCHES - 1), \
                patch("handlers.combat.database.set_user_flag") as set_user_flag:
            event = _select_research_event_by_chance(1, 1.0, 1.0, "зараженный_лес", 77)

        self.assertEqual(event, "anomaly")
        set_user_flag.assert_called_once_with(77, ANOMALY_GUARANTEE_FLAG, 0)

    def test_research_anomaly_event_is_blocked_without_location_pool(self):
        with patch("handlers.combat.database.get_user_flag", return_value=ANOMALY_GUARANTEE_RESEARCHES - 1), \
                patch("handlers.combat.database.set_user_flag") as set_user_flag, \
                patch("handlers.combat.random.randint", return_value=1), \
                patch("handlers.combat.random.uniform", return_value=10**9):
            event = _select_research_event_by_chance(95, 1.0, 1.0, "дорога_зараженный_лес", 77)

        self.assertNotEqual(event, "anomaly")
        set_user_flag.assert_not_called()

    def test_spawn_item_uses_location_drop_chance_as_weight_not_second_failure_roll(self):
        class Inventory:
            total_weight = 0

            def reload(self):
                pass

        class Player:
            current_location_id = "дорога_зараженный_лес"
            level = 5
            rare_find_chance = 0
            max_weight = 20
            inventory = Inventory()

        class Messages:
            def __init__(self):
                self.sent = []

            def send(self, **kwargs):
                self.sent.append(kwargs)
                return 1

        class Vk:
            def __init__(self):
                self.messages = Messages()

        trash_item = {
            "name": "Пустой фильтр",
            "category": "trash",
            "price": 1,
            "weight": 0.05,
            "location_drop_chances": {"дорога_зараженный_лес": 1},
        }
        vk = Vk()

        with patch("handlers.combat.database.get_item_by_name", return_value=None), \
                patch("handlers.combat.database.get_items_by_category", side_effect=lambda category: [trash_item] if category == "trash" else []), \
                patch("handlers.combat.database.get_item_location_drop_chance", return_value=1), \
                patch("handlers.combat.database.add_item_to_inventory", return_value=True) as add_item:
            _spawn_item(Player(), vk, 1)

        add_item.assert_called_once_with(1, "Пустой фильтр", 1)
        self.assertIn("Пустой фильтр", vk.messages.sent[0]["message"])

    def test_anomaly_buttons_are_callbacks(self):
        keyboard = json.loads(create_anomaly_keyboard(shells=1).get_keyboard())
        bypass = keyboard["buttons"][0][0]
        extract = keyboard["buttons"][0][1]

        self.assertTrue(keyboard["inline"])
        self.assertEqual(json.loads(bypass["action"]["payload"]), {"command": "anomaly_action", "action": "bypass"})
        self.assertEqual(json.loads(extract["action"]["payload"]), {"command": "anomaly_action", "action": "extract"})

    def test_anomaly_extract_hidden_without_shells(self):
        keyboard = json.loads(create_anomaly_keyboard(shells=0).get_keyboard())
        first_row = keyboard["buttons"][0]

        self.assertEqual(len(first_row), 1)
        self.assertEqual(json.loads(first_row[0]["action"]["payload"])["action"], "bypass")

    def test_anomaly_precise_extract_visible_with_three_shells(self):
        keyboard = json.loads(create_anomaly_keyboard(shells=3).get_keyboard())
        precise = keyboard["buttons"][1][0]

        self.assertEqual(precise["action"]["label"], "Точный бросок x3")
        self.assertEqual(
            json.loads(precise["action"]["payload"]),
            {"command": "anomaly_action", "action": "extract_precise"},
        )

    def test_combat_shell_decoy_visible_when_shells_available(self):
        with patch("handlers.combat.database.get_user_shells", return_value=2):
            keyboard = json.loads(create_combat_keyboard(DummyClassPlayer(), user_id=1).get_keyboard())

        decoy = keyboard["buttons"][2][0]
        self.assertEqual(decoy["action"]["label"], "Отвлечь x2")
        self.assertEqual(
            json.loads(decoy["action"]["payload"]),
            {"command": "combat_action", "action": "shell_decoy"},
        )

    def test_combat_shell_decoy_spends_shells_and_reduces_damage(self):
        class Player:
            health = 50
            max_health = 100
            energy = 40
            max_energy = 100
            total_defense = 3
            level = 20
            damage_resist = 0
            effective_stamina = 1

        class Messages:
            def __init__(self):
                self.sent = []
                self.edited = []

            def send(self, **kwargs):
                self.sent.append(kwargs)
                return 1

            def edit(self, **kwargs):
                self.edited.append(kwargs)
                return 1

        class Vk:
            def __init__(self):
                self.messages = Messages()

        player = Player()
        vk = Vk()
        set_combat_state(77, {
            "combat_id": "fight-77",
            "enemy_name": "Зомби",
            "enemy_hp": 20,
            "enemy_max_hp": 20,
            "enemy_damage": 20,
        })
        set_ui_message(77, "combat", 55, peer_id=77)

        with patch("handlers.combat.database.get_user_shells", return_value=2), \
                patch("handlers.combat.database.remove_shells", return_value=True) as remove_shells, \
                patch("handlers.combat.database.update_user_stats") as update_stats:
            handle_combat_shell_decoy(player, vk, 77)

        remove_shells.assert_called_once_with(77, 2)
        update_stats.assert_called_once_with(77, health=43, energy=40)
        self.assertEqual(player.health, 43)
        self.assertIn("20 → 10", vk.messages.edited[0]["message"])

    def test_artifact_damage_boost_applies_to_full_attack_damage(self):
        class Player:
            _artifact_bonuses = {"damage_boost": 12}

            def _get_passive_bonuses(self):
                return {}

        damage, bonus_pct = _apply_weapon_damage_bonus(Player(), 100)

        self.assertEqual(damage, 112)
        self.assertEqual(bonus_pct, 12)

    def test_knife_damage_bonus_applies_only_to_knives(self):
        class Player:
            _artifact_bonuses = {}

            def _get_passive_bonuses(self):
                return {"weapon_damage": 6, "knife_damage": 10}

        generic_damage, generic_bonus = _apply_weapon_damage_bonus(Player(), 100)
        knife_damage, knife_bonus = _apply_weapon_damage_bonus(Player(), 100, weapon_is_knife=True)

        self.assertEqual(generic_damage, 106)
        self.assertEqual(generic_bonus, 6)
        self.assertEqual(knife_damage, 115)
        self.assertEqual(knife_bonus, 16)

    def test_inline_combat_keyboard_has_no_back_button(self):
        keyboard = json.loads(create_combat_keyboard(DummyClassPlayer(), user_id=1).get_keyboard())

        self.assertNotIn("Назад", json.dumps(keyboard, ensure_ascii=False))

    def test_combat_inventory_keyboard_has_only_back_button(self):
        set_combat_state(1, {"combat_id": "fight-1"})

        keyboard = json.loads(create_combat_inventory_keyboard(user_id=1).get_keyboard())

        self.assertTrue(keyboard["inline"])
        self.assertEqual(len(keyboard["buttons"]), 1)
        self.assertEqual(len(keyboard["buttons"][0]), 1)
        button = keyboard["buttons"][0][0]
        self.assertEqual(button["action"]["label"], "Назад к бою")
        self.assertEqual(
            json.loads(button["action"]["payload"]),
            {"command": "combat_action", "action": "back", "combat_id": "fight-1"},
        )

    def test_combat_inventory_keyboard_shows_only_available_quick_items(self):
        set_combat_state(1, {"combat_id": "fight-1"})

        keyboard = json.loads(
            create_combat_inventory_keyboard(
                user_id=1,
                quick_items=[
                    {"name": "Бинт", "quantity": 2},
                    {"name": "Аптечка", "quantity": 1},
                ],
            ).get_keyboard()
        )

        labels = [
            button["action"]["label"]
            for row in keyboard["buttons"]
            for button in row
        ]
        payload = json.loads(keyboard["buttons"][0][0]["action"]["payload"])

        self.assertEqual(labels, ["Бинт x2", "Аптечка x1", "Назад к бою"])
        self.assertEqual(
            payload,
            {
                "command": "combat_action",
                "action": "use_item",
                "combat_id": "fight-1",
                "item": "Бинт",
            },
        )

    def test_combat_inventory_edits_active_combat_message(self):
        from handlers.commands import handle_combat_commands

        class Inventory:
            other = [{"name": "Бинт", "quantity": 2}]

            def reload(self):
                pass

        class Player:
            inventory = Inventory()
            player_class = None

        class Messages:
            def __init__(self):
                self.sent = []
                self.edited = []

            def send(self, **kwargs):
                self.sent.append(kwargs)
                return 101

            def edit(self, **kwargs):
                self.edited.append(kwargs)
                return 1

        class Vk:
            def __init__(self):
                self.messages = Messages()

        vk = Vk()
        set_combat_state(77, {"combat_id": "fight-77"})
        set_ui_message(77, "combat", 55, peer_id=77)

        handled = handle_combat_commands(Player(), vk, 77, "инвентарь", "Инвентарь")

        self.assertTrue(handled)
        self.assertEqual(vk.messages.sent, [])
        self.assertEqual(len(vk.messages.edited), 1)
        edited = vk.messages.edited[0]
        self.assertEqual(edited["message_id"], 55)
        self.assertIn("БОЕВОЙ ИНВЕНТАРЬ", edited["message"])
        self.assertIn("Бинт x2", edited["message"])
        self.assertNotIn("Атаковать", edited["keyboard"])
        self.assertIn("Назад к бою", edited["keyboard"])

    def test_combat_item_use_edits_back_to_combat_hud(self):
        from handlers.commands import handle_combat_commands

        class Inventory:
            other = [{"name": "Бинт", "quantity": 1}]

            def reload(self):
                pass

        class Player:
            inventory = Inventory()
            player_class = None
            health = 50
            max_health = 100
            energy = 80
            total_defense = 5

            def use_item(self, item_name):
                self.health = 70
                return True, f"Использован {item_name}."

        class Messages:
            def __init__(self):
                self.sent = []
                self.edited = []

            def send(self, **kwargs):
                self.sent.append(kwargs)
                return 101

            def edit(self, **kwargs):
                self.edited.append(kwargs)
                return 1

        class Vk:
            def __init__(self):
                self.messages = Messages()

        vk = Vk()
        set_combat_state(
            77,
            {
                "combat_id": "fight-77",
                "enemy_name": "Слепой пёс",
                "enemy_hp": 12,
                "enemy_max_hp": 20,
            },
        )
        set_ui_message(77, "combat", 55, peer_id=77)

        handled = handle_combat_commands(Player(), vk, 77, "использовать 1", "использовать 1")

        self.assertTrue(handled)
        self.assertEqual(vk.messages.sent, [])
        self.assertEqual(len(vk.messages.edited), 1)
        edited = vk.messages.edited[0]
        self.assertEqual(edited["message_id"], 55)
        self.assertIn("Использован Бинт.", edited["message"])
        self.assertIn("Слепой пёс", edited["message"])
        self.assertIn("Атаковать", edited["keyboard"])
        self.assertIn("Инвентарь", edited["keyboard"])

    def test_combat_item_use_accepts_quantity_after_index(self):
        from handlers.commands import handle_combat_commands

        class Inventory:
            other = [{"name": "Аптечка", "quantity": 3}]

            def reload(self):
                pass

        class Player:
            inventory = Inventory()
            player_class = None
            health = 10
            max_health = 100
            energy = 80
            total_defense = 5
            used = 0

            def use_item(self, item_name):
                self.used += 1
                self.health = min(self.max_health, self.health + 10)
                return True, f"Использована {item_name} #{self.used}."

        class Messages:
            def __init__(self):
                self.sent = []
                self.edited = []

            def send(self, **kwargs):
                self.sent.append(kwargs)
                return 101

            def edit(self, **kwargs):
                self.edited.append(kwargs)
                return 1

        class Vk:
            def __init__(self):
                self.messages = Messages()

        player = Player()
        vk = Vk()
        set_combat_state(77, {"combat_id": "fight-77", "enemy_name": "Слепой пёс", "enemy_hp": 12, "enemy_max_hp": 20})
        set_ui_message(77, "combat", 55, peer_id=77)

        handled = handle_combat_commands(player, vk, 77, "использовать 1 3", "использовать 1 3")

        self.assertTrue(handled)
        self.assertEqual(player.used, 3)
        self.assertEqual(vk.messages.sent, [])
        self.assertEqual(len(vk.messages.edited), 1)
        self.assertIn("Аптечка x3", vk.messages.edited[0]["message"])

    def test_combat_item_use_accepts_quantity_after_name(self):
        from handlers.commands import handle_combat_commands

        class Inventory:
            other = [{"name": "Аптечка", "quantity": 2}]

            def reload(self):
                pass

        class Player:
            inventory = Inventory()
            player_class = None
            health = 10
            max_health = 100
            energy = 80
            total_defense = 5
            used = 0

            def use_item(self, item_name):
                self.used += 1
                return True, f"Использована {item_name} #{self.used}."

        class Messages:
            def __init__(self):
                self.sent = []
                self.edited = []

            def send(self, **kwargs):
                self.sent.append(kwargs)
                return 101

            def edit(self, **kwargs):
                self.edited.append(kwargs)
                return 1

        class Vk:
            def __init__(self):
                self.messages = Messages()

        player = Player()
        vk = Vk()
        set_combat_state(77, {"combat_id": "fight-77", "enemy_name": "Слепой пёс", "enemy_hp": 12, "enemy_max_hp": 20})
        set_ui_message(77, "combat", 55, peer_id=77)

        handled = handle_combat_commands(player, vk, 77, "использовать аптечка 2", "использовать аптечка 2")

        self.assertTrue(handled)
        self.assertEqual(player.used, 2)
        self.assertEqual(vk.messages.sent, [])
        self.assertEqual(len(vk.messages.edited), 1)
        self.assertIn("Аптечка x2", vk.messages.edited[0]["message"])

    def test_text_message_does_not_reset_combat_edit_target(self):
        import main

        class Obj:
            message = {"from_id": 77}

        class Event:
            obj = Obj()

        with patch("main.is_in_combat", return_value=True), \
             patch("main.invalidate_edit_targets") as invalidate, \
             patch("main.handle_message"):
            main._process_message_event(Event(), object())

        invalidate.assert_not_called()

    def test_busy_user_lock_sends_message_and_skips_processing(self):
        import main

        class Obj:
            message = {"from_id": 99077}

        class Event:
            obj = Obj()

        class Messages:
            def __init__(self):
                self.sent = []

            def send(self, **kwargs):
                self.sent.append(kwargs)
                return 1

        class Vk:
            def __init__(self):
                self.messages = Messages()

        lock = main._get_user_lock(99077)
        self.assertTrue(lock.acquire(blocking=False))
        vk = Vk()
        try:
            with patch.object(main.config, "BOT_USER_LOCK_TIMEOUT", 0.01), \
                 patch.object(main, "_maybe_cleanup_inactive_states"), \
                 patch.object(main, "handle_message") as handle_message:
                main._process_message_event(Event(), vk)
        finally:
            lock.release()

        handle_message.assert_not_called()
        self.assertEqual(len(vk.messages.sent), 1)
        self.assertIn("Предыдущее действие", vk.messages.sent[0]["message"])

    def test_research_start_replaces_lower_keyboard_with_research_controls(self):
        class Inventory:
            total_weight = 0

        class Player:
            current_location_id = "дорога_военная_часть"
            energy = 100
            find_chance = 40
            rare_find_chance = 5
            inventory = Inventory()

            def _get_passive_bonuses(self):
                return {}

        class Messages:
            def __init__(self):
                self.sent = []

            def send(self, **kwargs):
                self.sent.append(kwargs)
                return 101

        class Vk:
            def __init__(self):
                self.messages = Messages()

        class FakeTimer:
            daemon = False

            def __init__(self, *args, **kwargs):
                pass

            def start(self):
                pass

        vk = Vk()

        with patch("handlers.combat.threading.Timer", FakeTimer), \
                patch("handlers.combat.database.update_user_stats", return_value=True):
            handle_explore_time(Player(), vk, 88, time_sec=5)

        self.assertTrue(is_researching(88))
        keyboard = vk.messages.sent[-1]["keyboard"]
        self.assertIn("Статус исследования", keyboard)
        self.assertIn("Отмена", keyboard)
        self.assertNotIn("Исследовать", keyboard)
        self.assertNotIn("Карта", keyboard)
        self.assertNotIn("Персонаж", keyboard)

    def test_many_skills_fall_back_to_lower_keyboard(self):
        class FakeClass:
            active_skills = [
                {"name": f"Навык {idx}", "energy_cost": 5, "cooldown": 1, "effect": {}}
                for idx in range(5)
            ]

        with patch("models.classes.get_class", return_value=FakeClass()):
            keyboard = json.loads(create_skills_keyboard(DummyClassPlayer(), user_id=1, inline=True).get_keyboard())

        self.assertFalse(keyboard["inline"])


if __name__ == "__main__":
    unittest.main()
