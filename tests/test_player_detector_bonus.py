import types
import unittest

from models.player import Player


class DummyInventory:
    other = []

    def reload(self):
        pass


class PlayerDetectorBonusTest(unittest.TestCase):
    def test_find_chance_uses_equipped_detector_bonus(self):
        player = Player.__new__(Player)
        player.perception = 4
        player.equipped_device = "Эхо-1"
        player.inventory = DummyInventory()
        player._artifact_bonuses = {}
        player._get_passive_bonuses = types.MethodType(lambda self: {}, player)

        self.assertGreater(player.find_chance, 12)


if __name__ == "__main__":
    unittest.main()
