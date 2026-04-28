import json
import unittest
from unittest.mock import patch

from handlers.events import handle_event_callback, show_random_event
from handlers.keyboards import create_random_event_keyboard
from infra import state_manager


class _Messages:
    def __init__(self):
        self.sent = []
        self.edited = []

    def send(self, **kwargs):
        self.sent.append(kwargs)
        return 501

    def edit(self, **kwargs):
        self.edited.append(kwargs)
        return 1


class _Vk:
    def __init__(self):
        self.messages = _Messages()


class _Player:
    current_location_id = "город"
    level = 1
    health = 100
    energy = 100
    money = 0
    experience = 0


class RandomEventUiTests(unittest.TestCase):
    def setUp(self):
        state_manager.clear_pending_event(77)
        state_manager.invalidate_edit_targets(77)

    def tearDown(self):
        state_manager.clear_pending_event(77)
        state_manager.invalidate_edit_targets(77)

    def test_random_event_keyboard_can_be_inline_callback(self):
        event = {
            "type": "neutral",
            "choices": [{"label": "Поговорить"}, {"label": "Уйти"}],
        }

        keyboard = json.loads(create_random_event_keyboard(event, inline=True).get_keyboard())
        first_payload = json.loads(keyboard["buttons"][0][0]["action"]["payload"])
        skip_payload = json.loads(keyboard["buttons"][-1][0]["action"]["payload"])

        self.assertTrue(keyboard["inline"])
        self.assertEqual(first_payload, {"command": "random_event", "action": "choice", "choice": 0})
        self.assertEqual(skip_payload, {"command": "random_event", "action": "skip"})

    def test_multistage_event_callback_edits_existing_screen(self):
        event = {
            "id": "talk",
            "type": "multi_stage",
            "stages": [
                {
                    "text": "Сталкер смотрит на тебя.",
                    "choices": [{"label": "Слушать", "next_stage": 1}],
                },
                {
                    "text": "Он рассказывает новость.",
                    "choices": [{"label": "Кивнуть", "is_final": True}],
                },
            ],
        }
        state_manager.set_pending_event(77, event)
        vk = _Vk()
        player = _Player()

        show_random_event(player, vk, 77, event)
        with patch("handlers.events.database.update_user_stats", return_value=True):
            handled = handle_event_callback(player, vk, 77, {"action": "choice", "choice": 0})

        self.assertTrue(handled)
        self.assertEqual(len(vk.messages.sent), 1)
        self.assertEqual(len(vk.messages.edited), 1)
        self.assertEqual(vk.messages.edited[0]["message_id"], 501)
        self.assertIn("Он рассказывает новость.", vk.messages.edited[0]["message"])


if __name__ == "__main__":
    unittest.main()
