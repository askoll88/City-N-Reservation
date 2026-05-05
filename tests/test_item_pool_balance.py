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

    def test_backpacks_have_meaningful_long_trip_progression(self):
        backpacks = [item for item in ITEMS_POOL if item[1] == "backpacks"]
        self.assertGreaterEqual(len(backpacks), 4)

        previous_price = 0
        previous_bonus = 0
        previous_net = 0.0
        for name, _category, _desc, price, _attack, _defense, weight, bonus, *_rest in backpacks:
            net_capacity = float(bonus) - float(weight)
            self.assertGreater(price, previous_price, name)
            self.assertGreater(bonus, previous_bonus, name)
            self.assertGreater(net_capacity, previous_net, name)
            self.assertGreaterEqual(price / max(1, net_capacity), 50, name)
            previous_price = price
            previous_bonus = bonus
            previous_net = net_capacity

        starter = _by_name("Походный рюкзак")
        cargo = _by_name("Грузовой рюкзак")
        self.assertLessEqual(starter[7], 12)
        self.assertGreaterEqual(cargo[3], 10_000)
        self.assertGreaterEqual(cargo[6], 8.0)


if __name__ == "__main__":
    unittest.main()
