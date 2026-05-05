import unittest
from unittest.mock import patch

from game.weapon_dungeons import (
    DUNGEON_ENERGY_COST,
    DUNGEON_WAVES,
    format_warehouse17_menu,
    get_available_warehouse17_threats,
    grant_warehouse17_rewards,
    start_warehouse17_run,
)


class DummyPlayer:
    def __init__(self, rank_tier=1, energy=100):
        self.rank_tier = rank_tier
        self.energy = energy

    def _get_rank_tier(self):
        return self.rank_tier


class WeaponDungeonsTest(unittest.TestCase):
    def test_available_threats_follow_rank_weapon_progression(self):
        self.assertEqual([t.id for t in get_available_warehouse17_threats(1)], ["i"])
        self.assertEqual([t.id for t in get_available_warehouse17_threats(8)], ["i", "ii", "iii"])
        self.assertEqual([t.id for t in get_available_warehouse17_threats(24)], ["i", "ii", "iii", "iv", "v"])

    def test_menu_mentions_energy_and_three_waves(self):
        menu = format_warehouse17_menu(DummyPlayer(rank_tier=1, energy=100))
        self.assertIn(str(DUNGEON_ENERGY_COST), menu)
        self.assertIn(str(DUNGEON_WAVES), menu)
        self.assertIn("Угроза I", menu)

    def test_start_run_spends_energy_and_starts_combat(self):
        player = DummyPlayer(rank_tier=24, energy=100)
        with patch("game.weapon_dungeons.database.update_user_stats") as update_stats, \
             patch("handlers.combat.start_dungeon_combat", return_value=True) as start_combat:
            result = start_warehouse17_run(player, object(), 777, "угроза v")

        self.assertTrue(result["success"])
        self.assertEqual(player.energy, 60)
        update_stats.assert_called_once_with(777, energy=60)
        dungeon_run = start_combat.call_args.args[3]
        self.assertEqual(dungeon_run["wave"], 1)
        self.assertEqual(dungeon_run["waves_total"], 3)
        self.assertEqual(dungeon_run["threat_id"], "v")

    def test_rewards_are_granted_as_weapon_materials(self):
        with patch("game.weapon_dungeons.random.randint", return_value=1), \
             patch("game.weapon_dungeons.database.add_weapon_material", return_value=True) as add_material:
            rewards = grant_warehouse17_rewards(777, "v")

        names = {name for name, _qty in rewards}
        self.assertIn("Ядро оружейного резонанса", names)
        self.assertTrue(add_material.called)


if __name__ == "__main__":
    unittest.main()
