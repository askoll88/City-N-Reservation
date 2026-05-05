import importlib
import json
import sys
import types
import unittest
from unittest.mock import Mock

from handlers.keyboards import create_inventory_hud_keyboard, create_inventory_keyboard
from infra.state_manager import invalidate_edit_targets


class DummyKeyboard:
    def get_keyboard(self):
        return "{}"


class DummyVKMessages:
    def __init__(self):
        self.sent = []
        self.edited = []

    def send(self, **kwargs):
        self.sent.append(kwargs)
        return len(self.sent)

    def edit(self, **kwargs):
        self.edited.append(kwargs)
        return 1

class DummyVK:
    def __init__(self):
        self.messages = DummyVKMessages()


class DummyInventory:
    def __init__(self):
        self.weapons = [{"name": "ПМ", "quantity": 1, "attack": 10, "weight": 1.0}]
        self.armor = [{"name": "Куртка", "quantity": 1, "defense": 5, "weight": 2.0}]
        self.backpacks = [{"name": "Рюкзак", "quantity": 1, "backpack_bonus": 10, "weight": 1.5}]
        self.artifacts = [{"name": "Медуза", "quantity": 1, "weight": 0.5}]
        self.shells_bags = []
        self.other = [{"name": "Бинт", "quantity": 2, "weight": 0.1}]
        self.total_weight = 4.6

    def reload(self):
        pass


class DummyPlayer:
    def __init__(self):
        self.inventory_section = None
        self.inventory = DummyInventory()
        self.equipped_weapon = "ПМ"
        self.equipped_armor_head = None
        self.equipped_armor_body = "Куртка"
        self.equipped_armor_legs = None
        self.equipped_armor_hands = None
        self.equipped_armor_feet = None
        self.equipped_backpack = "Рюкзак"
        self.equipped_device = None
        self.equipped_artifacts = []
        self.artifact_slots = 3
        self.max_weight = 30
        self.money = 100
        self.current_location_id = "город"


class InventorySectionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Фейковый database и main, чтобы не тащить внешние зависимости
        cls.fake_db = types.ModuleType("database")
        cls.fake_db.update_user_stats = Mock()
        cls.fake_db.get_item_by_name = Mock(return_value={})
        sys.modules["database"] = cls.fake_db

        fake_main = types.ModuleType("main")
        fake_main.create_inventory_keyboard = lambda *args, **kwargs: DummyKeyboard()
        fake_main.create_location_keyboard = lambda *args, **kwargs: DummyKeyboard()
        sys.modules["main"] = fake_main

        cls.inventory_module = importlib.import_module("handlers.inventory")

    def setUp(self):
        self.fake_db.update_user_stats.reset_mock()
        self.vk = DummyVK()
        self.player = DummyPlayer()

    def test_show_weapons_sets_section_in_memory_only(self):
        self.inventory_module.show_weapons(self.player, self.vk, user_id=1)
        self.assertEqual(self.player.inventory_section, "weapons")
        self.fake_db.update_user_stats.assert_not_called()

    def test_show_armor_sets_section_in_memory_only(self):
        self.inventory_module.show_armor(self.player, self.vk, user_id=1)
        self.assertEqual(self.player.inventory_section, "armor")
        self.fake_db.update_user_stats.assert_not_called()

    def test_show_backpacks_sets_section_in_memory_only(self):
        self.inventory_module.show_backpacks(self.player, self.vk, user_id=1)
        self.assertEqual(self.player.inventory_section, "backpacks")
        self.fake_db.update_user_stats.assert_not_called()

    def test_show_artifacts_sets_section_in_memory_only(self):
        self.inventory_module.show_artifacts(self.player, self.vk, user_id=1)
        self.assertEqual(self.player.inventory_section, "artifacts")
        self.fake_db.update_user_stats.assert_not_called()

    def test_artifact_bonus_text_uses_shared_bonus_table(self):
        text = self.inventory_module._artifact_bonus_text({"name": "Кристальная колючка"})

        self.assertIn("крит +10%", text)
        self.assertIn("защита +25", text)
        self.assertIn("уклон +15%", text)
        self.assertNotIn("без бонусов", text)

    def test_show_other_sets_section_in_memory_only(self):
        self.inventory_module.show_other(self.player, self.vk, user_id=1)
        self.assertEqual(self.player.inventory_section, "other")
        self.fake_db.update_user_stats.assert_not_called()

    def test_handle_use_item_equips_endgame_detector_without_detector_word(self):
        self.player.inventory.other = [{"name": "Око Зоны", "quantity": 1, "weight": 0.3}]

        def equip_device(name):
            self.player.equipped_device = name
            return True, f"Надето устройство: {name}"

        self.player.equip_device = equip_device

        self.inventory_module.handle_use_item(self.player, "Око Зоны", self.vk, user_id=1)

        self.assertEqual(self.player.equipped_device, "Око Зоны")
        self.assertIn("Надето устройство: Око Зоны", self.vk.messages.sent[0]["message"])

    def test_inventory_sections_edit_existing_inventory_screen(self):
        self.inventory_module.show_all(self.player, self.vk, user_id=9901)
        self.inventory_module.show_weapons(self.player, self.vk, user_id=9901)

        self.assertEqual(len(self.vk.messages.sent), 1)
        self.assertEqual(len(self.vk.messages.edited), 1)
        self.assertEqual(self.vk.messages.edited[0]["peer_id"], 9901)
        self.assertEqual(self.vk.messages.edited[0]["message_id"], 1)
        self.assertIn("ИНВЕНТАРЬ: ОРУЖИЕ", self.vk.messages.edited[0]["message"])

    def test_inventory_section_buttons_are_callbacks(self):
        keyboard = json.loads(create_inventory_keyboard().get_keyboard())
        first_button = keyboard["buttons"][0][0]
        payload = json.loads(first_button["action"]["payload"])

        self.assertEqual(first_button["action"]["type"], "callback")
        self.assertEqual(payload, {"command": "inventory_section", "section": "weapons"})

    def test_inventory_keyboard_stays_lower_ui_even_if_inline_requested(self):
        keyboard = json.loads(create_inventory_keyboard(inline=True).get_keyboard())

        self.assertFalse(keyboard["inline"])
        self.assertIn("Назад", json.dumps(keyboard, ensure_ascii=False))

    def test_inventory_back_button_uses_inventory_back_callback(self):
        keyboard = json.loads(create_inventory_keyboard().get_keyboard())
        back_button = keyboard["buttons"][-1][0]
        payload = json.loads(back_button["action"]["payload"])

        self.assertEqual(back_button["action"]["type"], "callback")
        self.assertEqual(payload, {"command": "inventory_back"})

    def test_inventory_hud_keyboard_has_section_and_page_callbacks(self):
        keyboard = json.loads(create_inventory_hud_keyboard(section="weapons", page=0, total_pages=3).get_keyboard())
        first_button = keyboard["buttons"][0][0]
        page_buttons = keyboard["buttons"][3]
        exit_button = keyboard["buttons"][4][0]

        self.assertTrue(keyboard["inline"])
        self.assertEqual(json.loads(first_button["action"]["payload"]), {"command": "inventory_section", "section": "weapons"})
        self.assertEqual(json.loads(page_buttons[0]["action"]["payload"]), {"command": "inventory_page", "section": "weapons", "page": 2})
        self.assertEqual(json.loads(page_buttons[1]["action"]["payload"]), {"command": "inventory_page", "section": "weapons", "page": 0})
        self.assertEqual(json.loads(page_buttons[2]["action"]["payload"]), {"command": "inventory_page", "section": "weapons", "page": 1})
        self.assertEqual(json.loads(exit_button["action"]["payload"]), {"command": "inventory_back"})

    def test_inventory_section_outputs_ten_items_per_page(self):
        invalidate_edit_targets(8801)
        self.player.inventory.weapons = [
            {"name": f"ПМ-{idx:02d}", "quantity": 1, "attack": idx, "weight": 1.0}
            for idx in range(1, 13)
        ]

        self.inventory_module.show_weapons(self.player, self.vk, user_id=8801, page=0)
        first_page = self.vk.messages.sent[0]["message"]
        self.inventory_module.show_weapons(self.player, self.vk, user_id=8801, page=1)
        second_page = self.vk.messages.edited[-1]["message"]

        self.assertIn("Страница: 1/2", first_page)
        self.assertIn("1. 🔫 ПМ-01", first_page)
        self.assertIn("10. 🔫 ПМ-10", first_page)
        self.assertNotIn("11. 🔫 ПМ-11", first_page)
        self.assertIn("Страница: 2/2", second_page)
        self.assertIn("11. 🔫 ПМ-11", second_page)
        self.assertIn("12. 🔫 ПМ-12", second_page)
        self.assertNotIn("10. 🔫 ПМ-10", second_page)


if __name__ == "__main__":
    unittest.main()
