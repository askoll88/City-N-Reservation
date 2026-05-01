import unittest
from unittest.mock import patch

from models.player import Player, calculate_player_max_health


class RankXpProgressionTests(unittest.TestCase):
    def _player(self):
        player = Player.__new__(Player)
        player.user_id = 1001
        player.level = 4
        player.experience = Player.LEVELS[5] - 50
        player.stamina = 4
        player.strength = 4
        player.perception = 4
        player.luck = 4
        player.energy = 50
        player.max_health_bonus = 0
        player.max_weight = 28
        player.player_class = None
        player._artifact_bonuses = {}
        player._last_level_up_message = None
        player._get_current_rank_level_cap = lambda: 4
        player._check_level_up = lambda persist=True: None
        return player

    def test_xp_clamps_at_rank_cap_threshold(self):
        player = self._player()
        cap_threshold = Player.LEVELS[5]

        with patch("models.player.database.update_user_stats"):
            gained = player.add_experience(999)
            blocked = player.add_experience(10)

        self.assertEqual(gained, 50)
        self.assertEqual(blocked, 0)
        self.assertEqual(player.experience, cap_threshold)

    def test_rank_unlock_moves_to_next_rank_start_without_overflow(self):
        player = self._player()
        player.experience = Player.LEVELS[5] + 500

        with patch("models.player.database.update_user_stats") as update_stats, \
                patch("models.player.database.increment_user_flag"), \
                patch("models.player.database.set_user_flag"), \
                patch("models.player.database.get_user_flag", return_value=0):
            player._apply_rank_unlock_progression(2)

        self.assertEqual(player.level, 5)
        self.assertEqual(player.experience, Player.LEVELS[5])
        self.assertEqual(player.energy, 100)
        self.assertEqual(player.health, calculate_player_max_health(5, 4, 0))
        update_stats.assert_called()


if __name__ == "__main__":
    unittest.main()
