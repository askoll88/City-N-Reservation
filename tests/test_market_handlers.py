import unittest
import json
from unittest.mock import Mock, patch

from handlers import market
from handlers.keyboards import create_market_pagination_keyboard


class DummyKeyboard:
    def get_keyboard(self):
        return "{}"


class DummyVKMessages:
    def __init__(self):
        self.send = Mock()


class DummyVK:
    def __init__(self):
        self.messages = DummyVKMessages()


class DummyPlayer:
    level = 10
    money = 1000


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

    @patch("handlers.market.create_purchase_confirm_keyboard", return_value=DummyKeyboard())
    @patch("handlers.market.database.get_item_by_name", return_value={"name": "ПМ", "category": "weapons", "attack": 15})
    @patch("handlers.market.database.get_market_listing_info")
    def test_handle_market_buy_listing_starts_confirmation(self, listing_info_mock, _item_mock, _kbd_mock):
        listing_info_mock.return_value = {
            "seller_vk_id": 2,
            "item_name": "ПМ",
            "quantity": 1,
            "price_per_item": 200,
            "category": "weapons",
            "rarity": "common",
        }

        handled = market.handle_market_buy_listing(
            player=DummyPlayer(),
            vk=self.vk,
            user_id=1,
            text="купить лот 15",
        )

        self.assertTrue(handled)
        listing_info_mock.assert_called_once_with(15)
        self.vk.messages.send.assert_called_once()

    @patch("handlers.market.create_player_market_keyboard", return_value=DummyKeyboard())
    @patch("handlers.quests.track_quest_market_buy")
    @patch("handlers.market.database.buy_market_listing")
    def test_handle_market_confirm_purchase_buys_listing(self, buy_listing_mock, _quest_mock, _kbd_mock):
        buy_listing_mock.return_value = {"success": True, "message": "bought"}
        market.set_pending_purchase(1, {
            "listing_id": 15,
            "item_name": "ПМ",
            "quantity": 1,
            "price_per_item": 200,
            "total_price": 200,
            "seller_vk_id": 2,
        })

        handled = market.handle_market_confirm_purchase(
            player=DummyPlayer(),
            vk=self.vk,
            user_id=1,
            text="подтвердить",
        )

        self.assertTrue(handled)
        buy_listing_mock.assert_called_once_with(1, 15)
        market.clear_pending_purchase(1)

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

    def test_market_pagination_buttons_are_callbacks(self):
        keyboard = json.loads(create_market_pagination_keyboard(1, 2).get_keyboard())
        next_button = keyboard["buttons"][0][0]
        payload = json.loads(next_button["action"]["payload"])

        self.assertEqual(next_button["action"]["type"], "callback")
        self.assertEqual(payload, {"command": "market_page", "page": 2})

    def test_market_sort_buttons_are_callbacks(self):
        keyboard = json.loads(create_market_pagination_keyboard(1, 1).get_keyboard())
        sort_button = keyboard["buttons"][1][0]
        payload = json.loads(sort_button["action"]["payload"])

        self.assertEqual(sort_button["action"]["type"], "callback")
        self.assertEqual(payload, {"command": "market_sort", "sort": "newest"})

    @patch("handlers.market.show_market_menu")
    def test_handle_market_callback_home_clears_state(self, show_menu_mock):
        market.set_market_browse_state(1, category="weapons", page=2, sort="cheap")

        handled = market.handle_market_callback(DummyPlayer(), self.vk, 1, {"command": "market_home"})

        self.assertTrue(handled)
        self.assertIsNone(market.get_market_browse_state(1))
        show_menu_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
