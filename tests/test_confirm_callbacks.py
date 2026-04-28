import json
import unittest

from handlers.keyboards import (
    create_emission_risk_confirm_keyboard,
    create_heal_confirm_keyboard,
    create_purchase_confirm_keyboard,
)


class ConfirmCallbackKeyboardTests(unittest.TestCase):
    def test_purchase_confirm_buttons_are_callbacks(self):
        keyboard = json.loads(create_purchase_confirm_keyboard().get_keyboard())
        confirm = keyboard["buttons"][0][0]
        cancel = keyboard["buttons"][0][1]

        self.assertEqual(json.loads(confirm["action"]["payload"]), {"command": "market_purchase", "action": "confirm"})
        self.assertEqual(json.loads(cancel["action"]["payload"]), {"command": "market_purchase", "action": "cancel"})

    def test_heal_confirm_buttons_are_callbacks(self):
        keyboard = json.loads(create_heal_confirm_keyboard().get_keyboard())
        confirm = keyboard["buttons"][0][0]
        cancel = keyboard["buttons"][0][1]

        self.assertEqual(json.loads(confirm["action"]["payload"]), {"command": "heal_confirm", "action": "confirm"})
        self.assertEqual(json.loads(cancel["action"]["payload"]), {"command": "heal_confirm", "action": "cancel"})

    def test_emission_risk_buttons_are_callbacks(self):
        keyboard = json.loads(create_emission_risk_confirm_keyboard().get_keyboard())
        confirm = keyboard["buttons"][0][0]
        cancel = keyboard["buttons"][1][0]

        self.assertEqual(json.loads(confirm["action"]["payload"]), {"command": "emission_risk", "action": "confirm"})
        self.assertEqual(json.loads(cancel["action"]["payload"]), {"command": "emission_risk", "action": "cancel"})


if __name__ == "__main__":
    unittest.main()
