import json
import random
import unittest
from unittest.mock import patch

from handlers.combat import (
    _hide_lower_keyboard_for_combat,
    _select_research_event_by_chance,
    _spawn_item,
    _will_continue_mutant_hunt,
    create_anomaly_keyboard,
    create_combat_keyboard,
    create_skills_keyboard,
    RESEARCH_EVENTS,
)
from infra.state_manager import clear_combat_state, set_combat_state


class DummyClassPlayer:
    player_class = "sniper"
    energy = 100


class CombatCallbackKeyboardTests(unittest.TestCase):
    def setUp(self):
        clear_combat_state(1)

    def tearDown(self):
        clear_combat_state(1)

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
            "name": "Пустая банка",
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

        add_item.assert_called_once_with(1, "Пустая банка", 1)
        self.assertIn("Пустая банка", vk.messages.sent[0]["message"])

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

    def test_inline_combat_keyboard_has_no_back_button(self):
        keyboard = json.loads(create_combat_keyboard(DummyClassPlayer(), user_id=1).get_keyboard())

        self.assertNotIn("Назад", json.dumps(keyboard, ensure_ascii=False))

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
