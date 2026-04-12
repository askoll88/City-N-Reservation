import unittest
from unittest.mock import Mock, patch

from handlers import admin


class DummyKeyboard:
    def get_keyboard(self):
        return "{}"


class DummyVKMessages:
    def __init__(self):
        self.send = Mock()


class DummyVK:
    def __init__(self):
        self.messages = DummyVKMessages()


class AdminHandlersTest(unittest.TestCase):
    def setUp(self):
        self.vk = DummyVK()
        self.player = object()

    @patch("handlers.admin.create_admin_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.database.is_user_admin", return_value=False)
    def test_denies_non_admin(self, _is_admin_mock, _kbd_mock):
        handled = admin.handle_admin_commands(
            self.player, self.vk, 1, "админка", "админка"
        )
        self.assertTrue(handled)
        self.vk.messages.send.assert_called_once()

    @patch("handlers.admin.create_admin_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.database.is_user_admin", return_value=True)
    @patch("handlers.admin.database.set_user_ban")
    def test_ban_command(self, set_ban_mock, _is_admin_mock, _kbd_mock):
        set_ban_mock.return_value = {"success": True, "message": "banned"}
        handled = admin.handle_admin_commands(
            self.player, self.vk, 1, "бан 777 причина", "бан 777 причина"
        )
        self.assertTrue(handled)
        set_ban_mock.assert_called_once_with(777, True, "причина")

    @patch("handlers.admin.create_admin_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.database.is_user_admin", return_value=True)
    @patch("handlers.admin.database.admin_set_user_field")
    def test_set_field_command(self, set_field_mock, _is_admin_mock, _kbd_mock):
        set_field_mock.return_value = {"success": True, "message": "ok"}
        handled = admin.handle_admin_commands(
            self.player, self.vk, 1, "админ set 777 money 15000", "админ set 777 money 15000"
        )
        self.assertTrue(handled)
        set_field_mock.assert_called_once_with(777, "money", 15000)

    @patch("handlers.admin.create_admin_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.database.is_user_admin", return_value=True)
    @patch("handlers.admin.database.set_game_setting")
    def test_market_toggle(self, set_game_setting_mock, _is_admin_mock, _kbd_mock):
        handled = admin.handle_admin_commands(
            self.player, self.vk, 1, "админ: маркет off", "админ: маркет off"
        )
        self.assertTrue(handled)
        set_game_setting_mock.assert_called_once_with("p2p_market_enabled", "0")


if __name__ == "__main__":
    unittest.main()
