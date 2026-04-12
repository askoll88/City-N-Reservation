import unittest
from unittest.mock import Mock, patch

from handlers import market


class DummyKeyboard:
    def get_keyboard(self):
        return "{}"


class DummyVKMessages:
    def __init__(self):
        self.send = Mock()


class DummyVK:
    def __init__(self):
        self.messages = DummyVKMessages()


class MarketHandlersTest(unittest.TestCase):
    def setUp(self):
        self.vk = DummyVK()

    @patch("handlers.market.create_player_market_keyboard", return_value=DummyKeyboard())
    @patch("handlers.market.database.create_market_listing")
    def test_handle_market_create_listing(self, create_listing_mock, _kbd_mock):
        create_listing_mock.return_value = {"success": True, "message": "ok"}

        handled = market.handle_market_create_listing(
            player=None,
            vk=self.vk,
            user_id=1,
            text="выставить ПМ 200 2",
        )

        self.assertTrue(handled)
        create_listing_mock.assert_called_once_with(1, "ПМ", 200, 2)

    @patch("handlers.market.create_player_market_keyboard", return_value=DummyKeyboard())
    @patch("handlers.market.database.buy_market_listing")
    def test_handle_market_buy_listing(self, buy_listing_mock, _kbd_mock):
        buy_listing_mock.return_value = {"success": True, "message": "bought"}

        handled = market.handle_market_buy_listing(
            player=None,
            vk=self.vk,
            user_id=1,
            text="купить лот 15",
        )

        self.assertTrue(handled)
        buy_listing_mock.assert_called_once_with(1, 15)

    @patch("handlers.market.create_player_market_keyboard", return_value=DummyKeyboard())
    @patch("handlers.market.database.cancel_market_listing")
    def test_handle_market_cancel_listing(self, cancel_listing_mock, _kbd_mock):
        cancel_listing_mock.return_value = {"success": True, "message": "cancelled"}

        handled = market.handle_market_cancel_listing(
            player=None,
            vk=self.vk,
            user_id=1,
            text="снять лот 9",
        )

        self.assertTrue(handled)
        cancel_listing_mock.assert_called_once_with(1, 9)


if __name__ == "__main__":
    unittest.main()
