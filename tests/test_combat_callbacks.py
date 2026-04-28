import json
import unittest
from unittest.mock import patch

from handlers.combat import (
    _hide_lower_keyboard_for_combat,
    _will_continue_mutant_hunt,
    create_anomaly_keyboard,
    create_combat_keyboard,
    create_skills_keyboard,
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
