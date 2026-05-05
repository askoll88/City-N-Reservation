import json
import unittest
from unittest.mock import patch

from handlers.events import handle_event_callback, show_random_event
from handlers.keyboards import create_random_event_keyboard
from game.random_events import _apply_random_loot, apply_event_choice
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

    def test_event_shells_and_reputation_are_persisted(self):
        event = {
            "id": "rep",
            "type": "neutral",
            "choices": [
                {
                    "label": "Помочь",
                    "effect": {"shells": 2, "reputation": 5, "message": "ok"},
                }
            ],
        }
        player = _Player()
        player.vk_id = 77
        player.reputation = {}

        with patch("game.random_events.database.get_user_shells", side_effect=[8, 10]), \
                patch("game.random_events.database.add_shells") as add_shells, \
                patch("game.random_events.database.increment_user_flag", return_value=5) as inc_flag, \
                patch("handlers.quests.track_quest_shells") as track_shells:
            result = apply_event_choice(event, 0, player, user_id=77)

        self.assertTrue(result["is_final"])
        add_shells.assert_called_once_with(77, 2)
        track_shells.assert_called_once_with(77, count=2)
        inc_flag.assert_called_once_with(77, "reputation:сталкеры", 5)
        self.assertEqual(player.reputation["сталкеры"], 5)

    def test_random_loot_shells_go_to_shell_counter_not_inventory_item(self):
        player = _Player()
        player.vk_id = 77

        with patch("game.random_events.random.randint", side_effect=[100, 1]), \
                patch("game.random_events.random.choice", return_value=("Гильзы", 10)), \
                patch("game.random_events.database.get_user_shells", side_effect=[0, 10]), \
                patch("game.random_events.database.add_shells") as add_shells, \
                patch("game.random_events.database.add_item_to_inventory") as add_item, \
                patch("handlers.quests.track_quest_shells"):
            loot = _apply_random_loot(player)

        add_shells.assert_called_once_with(77, 10)
        add_item.assert_not_called()
        self.assertEqual(loot["item"], "Гильзы x10")


if __name__ == "__main__":
    unittest.main()
