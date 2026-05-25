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
        self.users = Mock()


class AdminHandlersTest(unittest.TestCase):
    def setUp(self):
        self.vk = DummyVK()
        self.player = object()

    @patch("handlers.admin.create_admin_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.database.is_user_admin", return_value=False)
    def test_hides_admin_from_non_admin(self, _is_admin_mock, _kbd_mock):
        handled = admin.handle_admin_commands(
            self.player, self.vk, 1, "админка", "админка"
        )
        self.assertFalse(handled)
        self.vk.messages.send.assert_not_called()

    @patch("handlers.admin.create_admin_users_list_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.database.set_user_flag")
    @patch("handlers.admin.database.get_user_flag", return_value=0)
    @patch("handlers.admin.database.admin_search_users")
    @patch("handlers.admin.database.admin_count_users", return_value=12)
    @patch("handlers.admin.database.is_user_admin", return_value=True)
    def test_users_page_includes_vk_name(
        self,
        _is_admin_mock,
        _count_mock,
        search_mock,
        _get_flag_mock,
        _set_flag_mock,
        _kbd_mock,
    ):
        search_mock.return_value = [{
            "vk_id": 777,
            "name": "Сталкер",
            "level": 7,
            "experience": 159,
            "money": 446,
            "location": "убежище",
            "is_admin": 0,
            "is_banned": 0,
        }]
        self.vk.users.get.return_value = [{"id": 777, "first_name": "Иван", "last_name": "Петров"}]

        handled = admin.handle_admin_commands(
            self.player, self.vk, 1, "последние пользователи", "Последние пользователи"
        )

        self.assertTrue(handled)
        message = self.vk.messages.send.call_args.kwargs["message"]
        self.assertIn("Страница: 1/2", message)
        self.assertIn("Иван Петров", message)
        self.assertIn("ID: 777 | Ник: Сталкер", message)
        search_mock.assert_called_once_with(query=None, limit=10, offset=0)

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

    @patch("handlers.admin.create_admin_gacha_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.create_admin_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.database.is_user_admin", return_value=True)
    @patch("game.gacha.service.set_resonance_enabled")
    def test_gacha_toggle(self, set_enabled_mock, _is_admin_mock, _main_kbd_mock, _gacha_kbd_mock):
        handled = admin.handle_admin_commands(
            self.player, self.vk, 1, "админ: гача on", "админ: гача on"
        )
        self.assertTrue(handled)
        set_enabled_mock.assert_called_once_with(True)

    @patch("handlers.admin.create_admin_gacha_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.create_admin_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.database.is_user_admin", return_value=True)
    @patch("game.gacha.service.get_signal_shards", return_value=100)
    @patch("game.gacha.service.add_signal_shards", return_value=260)
    def test_gacha_give_shards(
        self,
        add_shards_mock,
        get_shards_mock,
        _is_admin_mock,
        _main_kbd_mock,
        _gacha_kbd_mock,
    ):
        handled = admin.handle_admin_commands(
            self.player, self.vk, 1, "админ гача осколки 777 160", "админ гача осколки 777 160"
        )
        self.assertTrue(handled)
        get_shards_mock.assert_called_once_with(777)
        add_shards_mock.assert_called_once_with(777, 160)

    @patch("handlers.admin.create_admin_events_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.create_admin_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.database.set_user_flag")
    @patch("handlers.admin.database.is_user_admin", return_value=True)
    def test_pale_watcher_admin_force_toggle_self_only(
        self,
        _is_admin_mock,
        set_flag_mock,
        _main_kbd_mock,
        _events_kbd_mock,
    ):
        handled = admin.handle_admin_commands(
            self.player, self.vk, 1, "админ долговязый on", "админ долговязый on"
        )

        self.assertTrue(handled)
        set_flag_mock.assert_called_once_with(1, "forest_hunting_pale_watcher_admin_force", 1)
        message = self.vk.messages.send.call_args.kwargs["message"]
        self.assertIn("включён", message)

    @patch("handlers.admin.create_admin_events_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.create_admin_keyboard", return_value=DummyKeyboard())
    @patch("handlers.admin.database.set_user_flag")
    @patch("handlers.admin.database.is_user_admin", return_value=True)
    def test_pale_watcher_admin_force_reset_clears_chain_and_enables_force(
        self,
        _is_admin_mock,
        set_flag_mock,
        _main_kbd_mock,
        _events_kbd_mock,
    ):
        handled = admin.handle_admin_commands(
            self.player, self.vk, 1, "админ долговязый сброс", "админ долговязый сброс"
        )

        self.assertTrue(handled)
        set_flag_mock.assert_any_call(1, "forest_hunting_pale_watcher_trail", 0)
        set_flag_mock.assert_any_call(1, "forest_hunting_pale_watcher_done", 0)
        set_flag_mock.assert_any_call(1, "forest_hunting_pale_watcher_admin_force", 1)


if __name__ == "__main__":
    unittest.main()
