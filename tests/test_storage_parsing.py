import json
import unittest
from unittest.mock import patch

from handlers.keyboards import create_storage_keyboard
from handlers.storage import _parse_transfer_payload, format_storage_page, show_storage, take_from_storage


class StorageParsingTest(unittest.TestCase):
    def test_parse_default_qty(self):
        qty, name = _parse_transfer_payload("Бинт")
        self.assertEqual(qty, 1)
        self.assertEqual(name, "Бинт")

    def test_parse_with_qty(self):
        qty, name = _parse_transfer_payload("3 Бинт")
        self.assertEqual(qty, 3)
        self.assertEqual(name, "Бинт")

    def test_parse_errors(self):
        res = _parse_transfer_payload("")
        self.assertIsNone(res[0])
        self.assertIn("Укажи предмет", res[1])

        res = _parse_transfer_payload("0 Бинт")
        self.assertIsNone(res[0])
        self.assertIn("Количество", res[1])

    def test_storage_keyboard_uses_callback_pagination(self):
        keyboard = create_storage_keyboard(page=0, total_pages=3).get_keyboard()
        buttons = json.loads(keyboard)["buttons"][0]
        payloads = [json.loads(button["action"]["payload"]) for button in buttons]

        self.assertEqual(buttons[0]["action"]["type"], "callback")
        self.assertEqual(payloads[0], {"command": "storage_page", "page": 2})
        self.assertEqual(payloads[1], {"command": "storage_page", "page": 0})
        self.assertEqual(payloads[2], {"command": "storage_page", "page": 1})

    def test_storage_page_outputs_ten_items(self):
        storage = [{"name": f"Item-{idx:02d}", "quantity": idx} for idx in range(1, 22)]
        load = {"current": len(storage), "capacity": 80}

        first_page, safe_page, total_pages = format_storage_page(storage, load, page=0)
        second_page, _, _ = format_storage_page(storage, load, page=1)

        self.assertEqual(safe_page, 0)
        self.assertEqual(total_pages, 3)
        self.assertIn("Страница: 1/3", first_page)
        self.assertIn("1. Item-01 x1", first_page)
        self.assertIn("10. Item-10 x10", first_page)
        self.assertNotIn("11. Item-11 x11", first_page)
        self.assertIn("Страница: 2/3", second_page)
        self.assertIn("11. Item-11 x11", second_page)
        self.assertIn("20. Item-20 x20", second_page)
        self.assertNotIn("10. Item-10 x10", second_page)

    def test_show_storage_uses_storage_hud(self):
        class Player:
            current_location_id = "убежище"
            level = 1

        storage = [{"name": "Бинт", "quantity": 3}]
        load = {"current": 1, "capacity": 80}
        with patch("handlers.storage.database.get_user_storage", return_value=storage), \
             patch("handlers.storage.database.get_user_storage_load", return_value=load), \
             patch("handlers.storage.get_ui_current_screen", return_value={"name": "location"}), \
             patch("handlers.storage.set_ui_screen") as set_ui_screen, \
             patch("handlers.storage.try_edit_or_send_ui") as send_ui:
            show_storage(Player(), object(), 777)

        set_ui_screen.assert_called_once()
        send_ui.assert_called_once()
        args, kwargs = send_ui.call_args
        self.assertEqual(args[2], "storage")
        self.assertIn("Бинт", args[3])
        self.assertIn("keyboard", kwargs)

    def test_take_from_storage_accepts_item_number(self):
        class Inventory:
            total_weight = 0

            def reload(self):
                pass

        class Player:
            current_location_id = "убежище"
            level = 1
            max_weight = 30
            inventory = Inventory()

        class Messages:
            def __init__(self):
                self.sent = []

            def send(self, **kwargs):
                self.sent.append(kwargs)
                return 1

        class Vk:
            messages = Messages()

        storage = [
            {"name": "Бинт", "quantity": 3, "weight": 0.1},
            {"name": "Аптечка", "quantity": 2, "weight": 0.4},
        ]
        load = {"current": 2, "capacity": 80}

        with patch("handlers.storage.database.get_user_storage", return_value=storage), \
             patch("handlers.storage.database.get_user_storage_load", return_value=load), \
             patch("handlers.storage.database.move_item_from_storage_transaction", return_value={"success": True, "message": "ok"}) as move_item, \
             patch("handlers.storage.get_ui_current_screen", return_value={"name": "storage", "page": 0}), \
             patch("handlers.storage.set_ui_screen"), \
             patch("handlers.storage.try_edit_or_send_ui"):
            take_from_storage(Player(), Vk(), 777, "2")

        move_item.assert_called_once_with(777, "Аптечка", 1)


if __name__ == "__main__":
    unittest.main()
