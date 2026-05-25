import unittest
from unittest.mock import patch

import infra.state_manager as state_manager
from handlers.location import go_back, go_to_location


class DummyPlayer:
    def __init__(self):
        self.user_id = 101
        self.current_location_id = "кпп"
        self.previous_location = "дорога_нии"
        self.level = 5

    @property
    def location(self):
        return type("Loc", (), {"name": "КПП", "description": "Контрольно-пропускной пункт."})()


class BackNavigationTests(unittest.TestCase):
    def setUp(self):
        state_manager.set_ui_screen(101, {"name": "location"}, clear_stack=True)

    def test_back_on_location_does_not_jump_to_previous_location(self):
        player = DummyPlayer()

        with patch("handlers.location.database.update_user_location") as update_location, \
                patch("handlers.location._send_location_message") as send_location:
            go_back(player, object(), player.user_id)

        self.assertEqual(player.current_location_id, "кпп")
        update_location.assert_not_called()
        send_location.assert_called_once()
        self.assertEqual(send_location.call_args.args[2], "кпп")

    def test_go_to_same_location_renders_overview_with_location_sender(self):
        player = DummyPlayer()
        player.current_location_id = "больница"

        with patch("handlers.location._send_location_message") as send_location, \
                patch("infra.state_manager.set_ui_screen"):
            go_to_location(player, "больница", object(), player.user_id)

        send_location.assert_called_once()
        self.assertEqual(send_location.call_args.args[2], "больница")


if __name__ == "__main__":
    unittest.main()
