import importlib
import sys
import types
import unittest
from unittest.mock import Mock


class DummyKeyboard:
    def get_keyboard(self):
        return "{}"


class DummyVKMessages:
    def __init__(self):
        self.send = Mock()


class DummyVK:
    def __init__(self):
        self.messages = DummyVKMessages()


class DummyInventory:
    def __init__(self):
        self.weapons = [{"name": "ПМ", "quantity": 1, "attack": 10, "weight": 1.0}]
        self.armor = [{"name": "Куртка", "quantity": 1, "defense": 5, "weight": 2.0}]
        self.backpacks = [{"name": "Рюкзак", "quantity": 1, "backpack_bonus": 10, "weight": 1.5}]
        self.artifacts = [{"name": "Медуза", "quantity": 1, "weight": 0.5}]
        self.other = [{"name": "Бинт", "quantity": 2, "weight": 0.1}]


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


class InventorySectionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Фейковый database и main, чтобы не тащить внешние зависимости
        cls.fake_db = types.ModuleType("database")
        cls.fake_db.update_user_stats = Mock()
        cls.fake_db.get_item_by_name = Mock(return_value={})
        sys.modules["database"] = cls.fake_db

        fake_main = types.ModuleType("main")
        fake_main.create_inventory_keyboard = lambda: DummyKeyboard()
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

    def test_show_other_sets_section_in_memory_only(self):
        self.inventory_module.show_other(self.player, self.vk, user_id=1)
        self.assertEqual(self.player.inventory_section, "other")
        self.fake_db.update_user_stats.assert_not_called()


if __name__ == "__main__":
    unittest.main()
