import unittest

from game.item_pool import ITEMS_POOL


def _rarity(item: tuple) -> str:
    return item[8] if len(item) >= 12 else "common"


def _by_name(name: str) -> tuple:
    for item in ITEMS_POOL:
        if item[0] == name:
            return item
    raise AssertionError(f"item not found: {name}")


class ItemPoolBalanceTest(unittest.TestCase):
    def test_powerful_legacy_items_are_not_common(self):
        expected = {
            "Экзоскелет": "legendary",
            "Бронекостюм": "epic",
            "Комбинезон сталкера": "epic",
            "Шлем спецназа": "legendary",
            "ТОЗ-34": "rare",
            "Ф-1": "legendary",
            "РГД-5": "legendary",
            "АК-74": "uncommon",
        }

        for item_name, rarity in expected.items():
            self.assertEqual(_rarity(_by_name(item_name)), rarity, item_name)

    def test_common_equipment_stays_starter_power(self):
        for item in ITEMS_POOL:
            if len(item) < 7:
                continue
            name, category, _desc, _price, attack, defense, _weight = item[:7]
            if _rarity(item) != "common":
                continue
            if category in {"weapons", "rare_weapons"}:
                self.assertLess(int(attack or 0), 30, name)
            if category in {"armor", "rare_armor"}:
                self.assertLess(int(defense or 0), 16, name)


if __name__ == "__main__":
    unittest.main()
