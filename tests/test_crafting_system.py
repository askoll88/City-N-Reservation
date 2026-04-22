import unittest

from game.crafting import (
    CRAFT_RECIPES,
    get_crafting_level_by_xp,
    get_recipe_by_index,
)


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


if __name__ == "__main__":
    unittest.main()
