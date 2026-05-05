import unittest
from unittest.mock import patch

from game.constants import NEWBIE_KIT_ITEMS
from game.crafting import (
    CRAFT_RECIPES,
    get_crafting_level_by_xp,
    get_recipe_by_index,
)
from game.item_pool import ITEMS_POOL
from handlers.keyboards import create_location_keyboard, create_weapon_upgrade_keyboard, create_workbench_keyboard
from handlers.crafting import show_weapon_upgrade_menu


class CraftingSystemTest(unittest.TestCase):
    def test_level_thresholds(self):
        self.assertEqual(get_crafting_level_by_xp(0), 1)
        self.assertEqual(get_crafting_level_by_xp(79), 1)
        self.assertEqual(get_crafting_level_by_xp(80), 2)
        self.assertEqual(get_crafting_level_by_xp(2250), 10)
        self.assertEqual(get_crafting_level_by_xp(999999), 10)

    def test_recipe_lookup_by_index(self):
        self.assertIsNone(get_recipe_by_index(0))
        self.assertIsNone(get_recipe_by_index(len(CRAFT_RECIPES) + 1))
        first = get_recipe_by_index(1)
        self.assertIsNotNone(first)
        self.assertEqual(first["id"], CRAFT_RECIPES[0]["id"])

    def test_shelter_opens_workbench_instead_of_raw_craft(self):
        shelter_keyboard = create_location_keyboard("убежище").get_keyboard()
        self.assertIn("Верстак", shelter_keyboard)
        self.assertNotIn("Крафт", shelter_keyboard)

        workbench_keyboard = create_workbench_keyboard().get_keyboard()
        self.assertIn("Крафт", workbench_keyboard)
        self.assertIn("Улучшение оружия", workbench_keyboard)

        weapon_keyboard = create_weapon_upgrade_keyboard().get_keyboard()
        self.assertIn("Улучшить оружие", weapon_keyboard)
        self.assertIn("Прорыв оружия", weapon_keyboard)

    def test_weapon_upgrade_menu_shows_only_equipped_weapon(self):
        class Inventory:
            weapons = [
                {"name": "ПМ", "attack": 10, "item_level": 1, "weapon_cap": 10, "weapon_ascension": 0, "item_rank": "common"},
                {"name": "АК-74", "attack": 40, "item_level": 5, "weapon_cap": 10, "weapon_ascension": 0, "item_rank": "rare"},
            ]

            def reload(self):
                return None

        class Player:
            current_location_id = "убежище"
            level = 1
            equipped_weapon = "ПМ"
            inventory = Inventory()

        class Messages:
            def __init__(self):
                self.sent = []

            def send(self, **kwargs):
                self.sent.append(kwargs)

        class Vk:
            def __init__(self):
                self.messages = Messages()

        vk = Vk()
        with patch("handlers.crafting.database.get_user_weapon_materials", return_value={}):
            show_weapon_upgrade_menu(Player(), vk, 777)

        message = vk.messages.sent[0]["message"]
        self.assertIn("Надетое оружие:", message)
        self.assertIn("ПМ", message)
        self.assertNotIn("АК-74", message)

    def test_newbie_kit_contains_basic_anomaly_detector(self):
        kit_items = {name for name, _quantity in NEWBIE_KIT_ITEMS}

        self.assertIn("Детектор Отклик-0", kit_items)

    def test_detector_upgrade_recipes_are_full_crafting_chain(self):
        expected_chain = [
            ("detector_otklik_1", "Детектор Отклик-0", "Детектор Отклик-1", 1),
            ("detector_otklik_m", "Детектор Отклик-1", "Детектор Отклик-М", 2),
            ("detector_scanner_p", "Детектор Отклик-М", "Детектор Сканер-П", 3),
            ("detector_peleng_3", "Детектор Сканер-П", "Детектор Пеленг-3", 4),
            ("detector_gnom_t", "Детектор Пеленг-3", "Детектор Гном-Т", 5),
            ("detector_x", "Детектор Гном-Т", "Детектор-Х", 6),
            ("detector_anomalist_2", "Детектор-Х", "Детектор Аномалист-2", 7),
            ("detector_mirage_alpha", "Детектор Аномалист-2", "Детектор Мираж-Альфа", 8),
            ("detector_oko_zony", "Детектор Мираж-Альфа", "Око Зоны", 10),
        ]
        recipes_by_id = {recipe["id"]: recipe for recipe in CRAFT_RECIPES}
        known_items = {item[0] for item in ITEMS_POOL}

        for recipe_id, previous_detector, result_detector, required_level in expected_chain:
            recipe = recipes_by_id.get(recipe_id)
            self.assertIsNotNone(recipe, recipe_id)
            self.assertIn((previous_detector, 1), recipe["ingredients"])
            self.assertEqual(recipe["result"], (result_detector, 1))
            self.assertEqual(recipe["required_level"], required_level)
            self.assertIn(result_detector, known_items)
            for ingredient_name, _quantity in recipe["ingredients"]:
                self.assertIn(ingredient_name, known_items)


if __name__ == "__main__":
    unittest.main()
