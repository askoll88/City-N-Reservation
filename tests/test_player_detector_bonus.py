import types
import unittest

from game.anomalies import DEVICES, get_detector_bonus, is_detector_name
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

    def test_detector_progression_bonus_grows_without_starter_spike(self):
        player = Player.__new__(Player)

        player.equipped_device = "Детектор Отклик-0"
        self.assertEqual(get_detector_bonus(player), 6)

        player.equipped_device = "Детектор Отклик-1"
        self.assertEqual(get_detector_bonus(player), 10)

        player.equipped_device = "Око Зоны"
        self.assertEqual(get_detector_bonus(player), 36)
        self.assertEqual(get_detector_bonus(player, in_cluster=True), 45)

    def test_detector_type_specialization_uses_higher_matching_bonus(self):
        player = Player.__new__(Player)
        player.equipped_device = "Детектор Сканер-П"

        self.assertEqual(get_detector_bonus(player), 16)
        self.assertEqual(get_detector_bonus(player, artifact_type="thermal"), 16)
        self.assertEqual(get_detector_bonus(player, artifact_type="electromagnetic"), 24)

    def test_detector_name_lookup_includes_endgame_detector_without_detector_word(self):
        self.assertTrue(is_detector_name("Око Зоны"))
        self.assertTrue(is_detector_name("детектор"))
        self.assertFalse(is_detector_name("Компас"))
        self.assertFalse(is_detector_name("Бинт"))
        self.assertFalse(is_detector_name("2"))

    def test_detector_x_to_anomalist_2_is_clear_upgrade(self):
        player = Player.__new__(Player)

        player.equipped_device = "Детектор-Х"
        self.assertEqual(get_detector_bonus(player), 24)
        self.assertEqual(get_detector_bonus(player, is_rare=True), 32)

        player.equipped_device = "Детектор Аномалист-2"
        self.assertEqual(get_detector_bonus(player), 29)
        self.assertEqual(get_detector_bonus(player, is_rare=True), 34)

        self.assertGreater(DEVICES["Детектор Аномалист-2"]["price"], DEVICES["Детектор-Х"]["price"])

    def test_detector_progression_prices_do_not_go_backwards_after_detector_x(self):
        names = ["Детектор-Х", "Детектор Аномалист-2", "Детектор Мираж-Альфа", "Око Зоны"]
        prices = [DEVICES[name]["price"] for name in names]
        base_bonuses = [DEVICES[name]["bonus_value"] for name in names]

        self.assertEqual(prices, sorted(prices))
        self.assertEqual(base_bonuses, sorted(base_bonuses))


if __name__ == "__main__":
    unittest.main()
