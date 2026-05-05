import unittest
from unittest.mock import Mock, patch

from handlers.commands import handle_blackmarket_commands, handle_dialog_commands
from infra.state_manager import clear_dialog_state, get_dialog_info, set_dialog_state


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
    current_location_id = "черный рынок"
    level = 1


class TraderUiCommandsTest(unittest.TestCase):
    def setUp(self):
        self.user_id = 92001
        clear_dialog_state(self.user_id)
        self.player = DummyPlayer()
        self.vk = DummyVK()

    def tearDown(self):
        clear_dialog_state(self.user_id)

    def test_sell_items_button_switches_from_buy_showcase_to_sell_showcase(self):
        set_dialog_state(self.user_id, "барыга", "buy_all")

        with patch("handlers.inventory.show_trader_shop_all") as show_buy, \
             patch("handlers.inventory.show_trader_sell_all") as show_sell:
            handled = handle_dialog_commands(
                self.player,
                self.vk,
                self.user_id,
                "продать предметы",
                "Продать предметы",
            )

        self.assertTrue(handled)
        show_sell.assert_called_once_with(self.player, self.vk, self.user_id)
        show_buy.assert_not_called()
        self.assertEqual(get_dialog_info(self.user_id)["stage"], "sell_all")

    def test_buy_items_button_switches_from_sell_showcase_to_buy_showcase(self):
        set_dialog_state(self.user_id, "барыга", "sell_all")

        with patch("handlers.inventory.show_trader_shop_all") as show_buy, \
             patch("handlers.inventory.show_trader_sell_all") as show_sell:
            handled = handle_dialog_commands(
                self.player,
                self.vk,
                self.user_id,
                "купить товары",
                "Купить товары",
            )

        self.assertTrue(handled)
        show_buy.assert_called_once_with(self.player, self.vk, self.user_id)
        show_sell.assert_not_called()
        self.assertEqual(get_dialog_info(self.user_id)["stage"], "buy_all")

    def test_blackmarket_sell_items_button_opens_sell_showcase(self):
        with patch("handlers.inventory.show_trader_shop_all") as show_buy, \
             patch("handlers.inventory.show_trader_sell_all") as show_sell, \
             patch("handlers.market.handle_market_input", return_value=False), \
             patch("handlers.market.handle_market_create_listing", return_value=False), \
             patch("handlers.market.handle_market_buy_listing", return_value=False), \
             patch("handlers.market.handle_market_cancel_listing", return_value=False):
            handled = handle_blackmarket_commands(
                self.player,
                self.vk,
                self.user_id,
                "продать предметы",
            )

        self.assertTrue(handled)
        show_sell.assert_called_once_with(self.player, self.vk, self.user_id)
        show_buy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
