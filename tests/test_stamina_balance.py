import unittest

from game.stat_balance import (
    next_stamina_max_energy_breakpoint,
    next_stamina_energy_regen_breakpoint,
    stamina_energy_regen,
    stamina_hp_bonus,
    stamina_max_energy_bonus,
    stamina_research_energy_discount,
)
from models.player import Player, calculate_player_max_health


class StaminaBalanceTests(unittest.TestCase):
    def test_early_hp_progression_keeps_existing_values(self):
        self.assertEqual(calculate_player_max_health(level=1, stamina=4), 100)
        self.assertEqual(calculate_player_max_health(level=10, stamina=4), 136)
        self.assertEqual(calculate_player_max_health(level=10, stamina=8), 176)

    def test_late_hp_has_diminishing_returns(self):
        self.assertGreater(stamina_hp_bonus(100), stamina_hp_bonus(20))
        self.assertGreater(stamina_hp_bonus(300), stamina_hp_bonus(100))
        self.assertLess(stamina_hp_bonus(300), 1000)

    def test_energy_regen_cannot_break_energy_resource(self):
        self.assertEqual(stamina_energy_regen(4), 0)
        self.assertGreater(stamina_energy_regen(100), stamina_energy_regen(20))
        self.assertLessEqual(stamina_energy_regen(300), 12)

    def test_energy_regen_breakpoint_is_visible_for_mid_stamina(self):
        self.assertEqual(stamina_energy_regen(8), 1)
        self.assertEqual(next_stamina_energy_regen_breakpoint(8), (12, 2))

    def test_stamina_adds_bounded_max_energy(self):
        self.assertEqual(stamina_max_energy_bonus(4), 0)
        self.assertGreater(stamina_max_energy_bonus(100), stamina_max_energy_bonus(20))
        self.assertLessEqual(stamina_max_energy_bonus(300), 40)
        self.assertEqual(next_stamina_max_energy_breakpoint(4), (6, 1))

    def test_research_discount_is_soft_capped(self):
        self.assertEqual(stamina_research_energy_discount(4), 0)
        self.assertGreater(stamina_research_energy_discount(100), stamina_research_energy_discount(20))
        self.assertLessEqual(stamina_research_energy_discount(300), 20)

    def test_level_297_all_stamina_stays_bounded(self):
        all_stamina = 4 + (Player.MAX_LEVEL - 1)
        self.assertEqual(all_stamina, 300)
        self.assertLess(calculate_player_max_health(Player.MAX_LEVEL, all_stamina), 2300)


if __name__ == "__main__":
    unittest.main()
