import unittest
from unittest.mock import patch

from game.stat_balance import rank_stat_cap
from game.weapon_dungeons import WAREHOUSE_17_THREATS
from handlers.combat import _build_dungeon_wave, _scale_enemy_for_fixed_level, _scale_enemy_for_player
from models.enemies import ENEMIES


class DummyPlayer:
    level = 167

    def __init__(self, rank_tier=16):
        self.rank_tier = rank_tier

    def _get_rank_tier(self):
        return self.rank_tier


class CombatBalanceScalingTest(unittest.TestCase):
    def test_normal_locations_do_not_rubberband_to_midgame_player_level(self):
        player = DummyPlayer(rank_tier=16)
        base_enemy = ENEMIES["дорога_военная_часть"][0]

        with patch("handlers.combat.random.randint", return_value=0), \
             patch("handlers.combat.random.choices", return_value=["bruiser"]), \
             patch("handlers.combat.random.random", return_value=1.0):
            enemy = _scale_enemy_for_player(player, base_enemy, "дорога_военная_часть")

        self.assertLess(enemy["enemy_level"], 45)
        self.assertGreaterEqual(enemy["enemy_level"], 1)

    def test_warehouse17_threat_levels_cover_midgame_domain_progression(self):
        self.assertEqual(
            [threat.enemy_level for threat in WAREHOUSE_17_THREATS],
            [12, 35, 70, 115, 165],
        )

    def test_high_warehouse17_threat_is_substantially_stronger_than_first_threat(self):
        player = DummyPlayer(rank_tier=16)
        base_enemy = ENEMIES["склад_17"][0]

        with patch("handlers.combat.random.choices", return_value=["bruiser"]), \
             patch("handlers.combat.random.random", return_value=1.0):
            low = _scale_enemy_for_fixed_level(player, base_enemy, 12)
            high = _scale_enemy_for_fixed_level(player, base_enemy, 165)

        self.assertGreater(high["enemy_hp"], low["enemy_hp"] * 8)
        self.assertGreater(high["enemy_damage"], low["enemy_damage"] * 5)

    def test_rank_stat_cap_opens_late_game_growth(self):
        self.assertEqual(rank_stat_cap(1), 20)
        self.assertGreaterEqual(rank_stat_cap(16), 70)
        self.assertEqual(rank_stat_cap(24), 100)

    def test_warehouse17_high_threats_raise_final_wave_elite_chance(self):
        player = DummyPlayer(rank_tier=16)
        base_enemy = ENEMIES["склад_17"][0]

        with patch("handlers.combat.enemies.get_enemy_for_location", return_value=base_enemy), \
             patch("handlers.combat.random.choices", return_value=["bruiser"]), \
             patch("handlers.combat.random.random", return_value=0.18), \
             patch("handlers.combat.random.randint", return_value=10):
            iv_combat, _ = _build_dungeon_wave(player, 1, {
                "id": "склад_17",
                "threat_id": "iv",
                "wave": 3,
                "waves_total": 3,
                "enemy_level": 115,
                "reward_mult": 2.3,
            })
            v_combat, _ = _build_dungeon_wave(player, 1, {
                "id": "склад_17",
                "threat_id": "v",
                "wave": 3,
                "waves_total": 3,
                "enemy_level": 165,
                "reward_mult": 3.0,
            })

        self.assertFalse(iv_combat["enemy_is_elite"])
        self.assertTrue(v_combat["enemy_is_elite"])

    def test_warehouse17_regular_threat_keeps_base_final_wave_elite_chance(self):
        player = DummyPlayer(rank_tier=16)
        base_enemy = ENEMIES["склад_17"][0]

        with patch("handlers.combat.enemies.get_enemy_for_location", return_value=base_enemy), \
             patch("handlers.combat.random.choices", return_value=["bruiser"]), \
             patch("handlers.combat.random.random", return_value=0.12), \
             patch("handlers.combat.random.randint", return_value=10):
            combat, _ = _build_dungeon_wave(player, 1, {
                "id": "склад_17",
                "threat_id": "iii",
                "wave": 3,
                "waves_total": 3,
                "enemy_level": 70,
                "reward_mult": 1.8,
            })

        self.assertFalse(combat["enemy_is_elite"])


if __name__ == "__main__":
    unittest.main()
