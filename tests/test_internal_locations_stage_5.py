import unittest
from unittest.mock import Mock, patch

from game.constants import (
    ITEM_CATEGORY_DROP_CHANCES_BY_LOCATION,
    LOCATION_DROP_BALANCE_RULES,
    LOCATION_LEVEL_THRESHOLDS,
    RESEARCH_LOCATIONS,
)
from game.map_access import can_enter_location
from game.map_schema import get_map_location
from handlers.commands import handle_navigation
from handlers.keyboards import create_location_keyboard, create_map_region_keyboard
from handlers.map_screen import format_region_map, get_next_map_step
from models.enemies import ENEMIES
from models.locations import LOCATIONS


class DummyInventory:
    weapons = []
    armor = []
    backpacks = []
    artifacts = []
    shells_bags = []
    other = []


class DummyPlayer:
    RANK_TIERS = [
        {"name": "Новичок", "min_level": 1, "max_level": 4},
        {"name": "Салага", "min_level": 5, "max_level": 8},
    ]

    def __init__(self, level=5, rank_tier=2, current_location_id="дорога_военная_часть"):
        self.user_id = 1
        self.level = level
        self.rank_tier = rank_tier
        self.current_location_id = current_location_id
        self.inventory = DummyInventory()

    def _get_rank_tier(self):
        return self.rank_tier


class InternalLocationsStage5Tests(unittest.TestCase):
    def test_internal_locations_are_research_locations_with_runtime_content(self):
        internal_ids = {"военная_часть", "главный_корпус_нии", "зараженный_лес"}
        self.assertTrue(internal_ids.issubset(set(RESEARCH_LOCATIONS)))

        for location_id in internal_ids:
            self.assertIn(location_id, LOCATIONS)
            self.assertIn(location_id, ENEMIES)
            self.assertIn(location_id, ITEM_CATEGORY_DROP_CHANCES_BY_LOCATION)
            self.assertIn(location_id, LOCATION_LEVEL_THRESHOLDS)
            self.assertIn(location_id, LOCATION_DROP_BALANCE_RULES)
            self.assertIn("research", get_map_location(location_id)["activities"])

    def test_internal_locations_are_second_layer_after_roads(self):
        self.assertEqual(LOCATIONS["дорога_военная_часть"]["exits"]["военная часть"], "военная_часть")
        self.assertEqual(LOCATIONS["военная_часть"]["exits"]["дорога на военную часть"], "дорога_военная_часть")
        self.assertEqual(LOCATIONS["дорога_нии"]["exits"]["главный корпус нии"], "главный_корпус_нии")
        self.assertEqual(LOCATIONS["главный_корпус_нии"]["exits"]["дорога на нии"], "дорога_нии")
        self.assertEqual(LOCATIONS["дорога_зараженный_лес"]["exits"]["зараженный лес"], "зараженный_лес")
        self.assertEqual(LOCATIONS["зараженный_лес"]["exits"]["дорога на зараженный лес"], "дорога_зараженный_лес")

    def test_access_blocks_underleveled_player_from_internal_layer(self):
        low_player = DummyPlayer(level=4, rank_tier=1)
        result = can_enter_location(low_player, "военная_часть")

        self.assertFalse(result.allowed)
        self.assertIn("уровень 5+", "\n".join(result.reasons))
        self.assertIn("ранг 2+", "\n".join(result.reasons))

    def test_map_routes_from_road_to_internal_location(self):
        command, text = get_next_map_step("military", "дорога_военная_часть")

        self.assertEqual(command, "Военная часть")
        self.assertIn("идти глубже", text)

        region_text = format_region_map(DummyPlayer(current_location_id="дорога_военная_часть"), "military")
        self.assertIn("Военная часть", region_text)

    def test_location_keyboards_offer_internal_step_and_map_does_not_duplicate_it(self):
        road_keyboard = create_location_keyboard("дорога_нии").get_keyboard()
        inner_keyboard = create_location_keyboard("главный_корпус_нии").get_keyboard()
        map_keyboard = create_map_region_keyboard("forest", "дорога_зараженный_лес").get_keyboard()

        self.assertIn("Главный корпус НИИ", road_keyboard)
        self.assertIn("Дорога на НИИ", inner_keyboard)
        self.assertNotIn("Зараженный лес", map_keyboard)
        self.assertIn("Лес", map_keyboard)

    def test_navigation_uses_existing_go_to_location_for_internal_steps(self):
        player = DummyPlayer(current_location_id="дорога_военная_часть")
        vk = Mock()
        with patch("handlers.commands.go_to_location") as go_to:
            handled = handle_navigation(player, vk, 1, "военная часть")

        self.assertTrue(handled)
        go_to.assert_called_once_with(player, "военная_часть", vk, 1)


if __name__ == "__main__":
    unittest.main()
