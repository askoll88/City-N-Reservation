import unittest

from models.player import calculate_player_max_health


class HpProgressionTests(unittest.TestCase):
    def test_level_one_default_stamina_keeps_starting_health(self):
        self.assertEqual(calculate_player_max_health(level=1, stamina=4), 100)

    def test_health_scales_from_level_stamina_and_bonus(self):
        self.assertEqual(calculate_player_max_health(level=10, stamina=4), 136)
        self.assertEqual(calculate_player_max_health(level=10, stamina=8), 176)
        self.assertEqual(calculate_player_max_health(level=10, stamina=8, max_health_bonus=25), 201)


if __name__ == "__main__":
    unittest.main()
