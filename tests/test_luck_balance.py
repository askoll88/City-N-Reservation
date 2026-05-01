import unittest

from game.stat_balance import luck_artifact_bonus, luck_crit_bonus, luck_outcome_bonus
from models.player import Player


class LuckBalanceTests(unittest.TestCase):
    def _player(self, luck: int, artifact_bonuses=None):
        player = Player.__new__(Player)
        player.luck = luck
        player._artifact_bonuses = artifact_bonuses or {}
        player._get_passive_bonuses = lambda: {}
        return player

    def test_luck_has_diminishing_returns(self):
        self.assertGreater(luck_crit_bonus(20), luck_crit_bonus(4))
        self.assertGreater(luck_crit_bonus(100), luck_crit_bonus(20))
        self.assertLessEqual(luck_crit_bonus(100), 28)

    def test_crit_never_becomes_guaranteed_from_luck(self):
        player = self._player(100)
        self.assertLess(player.crit_chance, 55)

    def test_artifact_and_event_luck_bonuses_are_soft_capped(self):
        self.assertLessEqual(luck_artifact_bonus(100), 18)
        self.assertLessEqual(luck_outcome_bonus(100), 18)

    def test_artifacts_cannot_push_crit_to_one_hundred_percent(self):
        player = self._player(100, {"crit": 60})
        self.assertEqual(player.crit_chance, 55)

    def test_rare_find_is_capped_below_guaranteed(self):
        player = self._player(100, {"rare_find_chance": 60})
        self.assertEqual(player.rare_find_chance, 45)


if __name__ == "__main__":
    unittest.main()
