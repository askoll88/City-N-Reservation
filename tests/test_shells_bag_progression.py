import unittest

from game.item_pool import ITEMS_POOL
from infra import config


def _item_by_name(name):
    for item in ITEMS_POOL:
        if item[0] == name:
            return item
    raise AssertionError(f"Item not found: {name}")


class ShellsBagProgressionTest(unittest.TestCase):
    def test_newbie_bag_is_small_starter_capacity(self):
        small_bag = _item_by_name("Маленький мешочек")

        self.assertEqual(small_bag[1], "shells_bag")
        self.assertEqual(small_bag[7], 10)
        self.assertIn("10 гильз", small_bag[2])

    def test_soldier_progression_starts_after_starter_bag(self):
        self.assertNotIn("Маленький мешочек", config.SHELLS_BAG_REQUIREMENTS)
        self.assertEqual(config.SHELLS_BAG_ORDER[0], "Средний мешочек")
        self.assertEqual(config.SHELLS_BAG_REQUIREMENTS["Средний мешочек"]["level"], 8)
        self.assertEqual(config.SHELLS_BAG_REQUIREMENTS["Легендарный мешочек"]["level"], 120)


if __name__ == "__main__":
    unittest.main()
