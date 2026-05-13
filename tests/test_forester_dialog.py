import unittest
from unittest.mock import patch

from handlers.commands import handle_navigation, handle_npc_selection


class DummyMessages:
    def __init__(self):
        self.sent = []

    def send(self, **kwargs):
        self.sent.append(kwargs)
        return len(self.sent)


class DummyVK:
    def __init__(self):
        self.messages = DummyMessages()


class DummyPlayer:
    def __init__(self, location_id="заимка_лесника", level=10):
        self.user_id = 1201
        self.current_location_id = location_id
        self.level = level


class ForesterDialogTests(unittest.TestCase):
    def test_forester_name_is_not_swallowed_by_forest_navigation(self):
        player = DummyPlayer()
        vk = DummyVK()

        handled = handle_navigation(player, vk, player.user_id, "лесник")

        self.assertFalse(handled)
        self.assertEqual(player.current_location_id, "заимка_лесника")
        self.assertEqual(vk.messages.sent, [])

    def test_forester_selection_opens_dialog_at_hut(self):
        player = DummyPlayer()
        vk = DummyVK()

        with patch("handlers.quests.track_quest_talk_npc"):
            handled = handle_npc_selection(player, vk, player.user_id, "лесник")

        self.assertTrue(handled)
        self.assertEqual(len(vk.messages.sent), 1)
        self.assertIn("Лесник", vk.messages.sent[0]["message"])


if __name__ == "__main__":
    unittest.main()
