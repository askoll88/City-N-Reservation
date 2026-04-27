import unittest
from unittest.mock import patch

from game.map_access import can_enter_location, get_required_rank_tier_for_level


class DummyInventory:
    def __init__(self):
        self.weapons = [{"name": "ПМ", "quantity": 1}]
        self.armor = [{"name": "Бронежилет", "quantity": 1}]
        self.backpacks = []
        self.artifacts = []
        self.shells_bags = []
        self.other = [{"name": "old_bunker_key", "quantity": 1}, {"name": "Антирад", "quantity": 2}]


class DummyPlayer:
    RANK_TIERS = [
        {"name": "Новичок", "min_level": 1, "max_level": 4},
        {"name": "Салага", "min_level": 5, "max_level": 8},
        {"name": "Ходок", "min_level": 9, "max_level": 13},
    ]

    def __init__(self):
        self.user_id = 1
        self.level = 5
        self.rank_tier = 2
        self.radiation = 20
        self.artifact_slots = 3
        self.money = 1000
        self.total_defense = 12
        self.equipped_weapon = "ПМ"
        self.equipped_armor = None
        self.equipped_armor_head = None
        self.equipped_armor_body = "Бронежилет"
        self.equipped_armor_legs = None
        self.equipped_armor_hands = None
        self.equipped_armor_feet = None
        self.equipped_backpack = None
        self.equipped_device = None
        self.equipped_shells_bag = None
        self.equipped_artifacts = []
        self.inventory = DummyInventory()
        self.reputation = {"ученые": 30}
        self.opened_nii_basement = 1

    def _get_rank_tier(self):
        return self.rank_tier


class MapAccessTests(unittest.TestCase):
    def test_current_access_allows_existing_route_when_level_and_rank_fit(self):
        player = DummyPlayer()
        result = can_enter_location(player, "дорога_зараженный_лес")
        self.assertTrue(result.allowed)
        self.assertEqual(result.reasons, [])

    def test_missing_location_is_blocked(self):
        result = can_enter_location(DummyPlayer(), "нет_такой_локации")
        self.assertFalse(result.allowed)
        self.assertIn("Локация не найдена", result.reasons[0])

    def test_level_min_blocks_entry(self):
        player = DummyPlayer()
        player.level = 2
        result = can_enter_location(player, "дорога_зараженный_лес")
        self.assertFalse(result.allowed)
        self.assertIn("уровень 3+ (сейчас 2)", result.reasons)

    def test_required_rank_is_inferred_from_location_level(self):
        self.assertEqual(get_required_rank_tier_for_level(1, DummyPlayer()), 1)
        self.assertEqual(get_required_rank_tier_for_level(5, DummyPlayer()), 2)
        self.assertEqual(get_required_rank_tier_for_level(9, DummyPlayer()), 3)

    def test_rank_gate_blocks_even_if_player_level_is_high_enough(self):
        player = DummyPlayer()
        player.level = 5
        player.rank_tier = 1
        result = can_enter_location(player, "дорога_зараженный_лес")
        self.assertTrue(result.allowed)  # forest still belongs to rank 1 by level_min=3

        with patch("game.map_access.get_map_location") as get_location:
            get_location.return_value = {
                "id": "test_high_zone",
                "name": "High Zone",
                "level_min": 5,
                "level_max": 8,
                "requires": {},
            }
            result = can_enter_location(player, "test_high_zone")
        self.assertFalse(result.allowed)
        self.assertIn("ранг 2+ (сейчас 1)", result.reasons)

    def test_explicit_requirements_are_checked(self):
        player = DummyPlayer()
        with patch("game.map_access.get_map_location") as get_location:
            get_location.return_value = {
                "id": "test_locked_zone",
                "name": "Locked Zone",
                "level_min": 5,
                "level_max": 10,
                "requires": {
                    "key": "old_bunker_key",
                    "items": ["Антирад"],
                    "flags": ["opened_nii_basement"],
                    "reputation": {"ученые": 25},
                    "equipped": ["Бронежилет"],
                    "radiation_max": 50,
                    "money": 500,
                    "defense": 10,
                },
            }
            result = can_enter_location(player, "test_locked_zone")
        self.assertTrue(result.allowed)

    def test_missing_explicit_requirements_are_reported(self):
        player = DummyPlayer()
        player.reputation = {"ученые": 5}
        player.total_defense = 1
        player.equipped_armor_body = None
        with patch("game.map_access.get_map_location") as get_location:
            get_location.return_value = {
                "id": "test_locked_zone",
                "name": "Locked Zone",
                "level_min": 5,
                "level_max": 10,
                "requires": {
                    "key": "missing_key",
                    "items": ["Дозиметр"],
                    "flags": ["missing_flag"],
                    "reputation": {"ученые": 25},
                    "equipped": ["Бронежилет"],
                    "defense": 10,
                },
            }
            result = can_enter_location(player, "test_locked_zone")
        self.assertFalse(result.allowed)
        text = "\n".join(result.reasons)
        self.assertIn("ключ: missing_key", text)
        self.assertIn("предметы: Дозиметр", text)
        self.assertIn("флаги: missing_flag", text)
        self.assertIn("репутация ученые: 25+ (сейчас 5)", text)
        self.assertIn("экипировка: Бронежилет", text)
        self.assertIn("защита 10+ (сейчас 1)", text)


if __name__ == "__main__":
    unittest.main()
