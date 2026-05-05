import unittest
from unittest.mock import patch

from infra import config, database


class TraderShopBalanceTest(unittest.TestCase):
    def test_trader_filters_epic_and_legendary_items_from_candidates(self):
        by_category = {
            "weapons": [
                {"id": 1, "name": "ПМ", "category": "weapons", "rarity": "common"},
                {"id": 2, "name": "АК-74", "category": "weapons", "rarity": "rare"},
                {"id": 3, "name": "АК-74М", "category": "weapons", "rarity": "epic"},
                {"id": 4, "name": "Винтовка Гаусса", "category": "weapons", "rarity": "legendary"},
            ],
            "armor": [
                {"id": 5, "name": "Кожаная куртка", "category": "armor", "rarity": "common"},
                {"id": 6, "name": "Комбинезон сталкера", "category": "armor", "rarity": "epic"},
            ],
            "meds": [],
            "food": [],
            "backpacks": [],
            "rare_weapons": [],
        }

        with patch("infra.database._get_cached_items", return_value=({}, by_category, {})):
            candidates = database._get_shop_candidates(database.NPC_MERCHANT_TRADER)

        names = {item["name"] for item in candidates}
        self.assertIn("ПМ", names)
        self.assertIn("АК-74", names)
        self.assertIn("Кожаная куртка", names)
        self.assertNotIn("АК-74М", names)
        self.assertNotIn("Винтовка Гаусса", names)
        self.assertNotIn("Комбинезон сталкера", names)

    def test_trader_gear_stock_is_single_copy(self):
        for item in (
            {"category": "weapons", "rarity": "common"},
            {"category": "rare_weapons", "rarity": "rare"},
            {"category": "armor", "rarity": "rare"},
            {"category": "backpacks", "rarity": "common"},
        ):
            with self.subTest(item=item):
                self.assertEqual(
                    database._initial_shop_stock(
                        item,
                        is_featured=True,
                        merchant_id=database.NPC_MERCHANT_TRADER,
                    ),
                    1,
                )

    def test_trader_essential_items_get_larger_stock(self):
        med_stock = database._initial_shop_stock(
            {"category": "meds", "rarity": "common"},
            is_featured=False,
            merchant_id=database.NPC_MERCHANT_TRADER,
        )
        featured_food_stock = database._initial_shop_stock(
            {"category": "food", "rarity": "rare"},
            is_featured=True,
            merchant_id=database.NPC_MERCHANT_TRADER,
        )

        bonus = database._TRADER_ESSENTIAL_STOCK_BONUS
        self.assertEqual(med_stock, config.SHOP_STOCK_DEFAULT + bonus)
        self.assertEqual(featured_food_stock, config.SHOP_STOCK_RARE + 1 + bonus)


if __name__ == "__main__":
    unittest.main()
