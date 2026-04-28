import json
import unittest

from handlers.combat import create_anomaly_keyboard, create_combat_keyboard


class DummyClassPlayer:
    player_class = "sniper"
    energy = 100


class CombatCallbackKeyboardTests(unittest.TestCase):
    def test_combat_attack_button_is_callback(self):
        keyboard = json.loads(create_combat_keyboard(DummyClassPlayer(), user_id=1).get_keyboard())
        button = keyboard["buttons"][0][0]
        payload = json.loads(button["action"]["payload"])

        self.assertTrue(keyboard["inline"])
        self.assertEqual(button["action"]["type"], "callback")
        self.assertEqual(payload, {"command": "combat_action", "action": "attack"})

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


if __name__ == "__main__":
    unittest.main()
