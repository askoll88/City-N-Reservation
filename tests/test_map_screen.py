import unittest

from handlers.keyboards import create_location_keyboard, create_map_overview_keyboard, create_map_region_keyboard
from handlers.map_screen import (
    format_map_overview,
    format_region_map,
    get_next_map_step,
)


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

    def __init__(self, level=1, rank_tier=1, current_location_id="город"):
        self.user_id = 1
        self.level = level
        self.rank_tier = rank_tier
        self.current_location_id = current_location_id
        self.inventory = DummyInventory()

    def _get_rank_tier(self):
        return self.rank_tier


class MapScreenTests(unittest.TestCase):
    def test_overview_shows_regions_not_full_location_list(self):
        player = DummyPlayer()
        text = format_map_overview(player)

        self.assertIn("Город", text)
        self.assertIn("Военный сектор", text)
        self.assertIn("НИИ", text)
        self.assertIn("Лес", text)
        self.assertNotIn("Больница:", text)
        self.assertNotIn("Черный рынок:", text)

    def test_danger_region_routes_through_kpp_from_city(self):
        command, text = get_next_map_step("science", "город")

        self.assertEqual(command, "КПП")
        self.assertIn("КПП", text)
        self.assertIn("Следующий шаг", text)

    def test_danger_region_opens_road_from_kpp(self):
        command, text = get_next_map_step("science", "кпп")

        self.assertEqual(command, "Дорога на НИИ")
        self.assertIn("Дорога на НИИ", text)

    def test_danger_region_routes_city_services_back_to_city_first(self):
        command, text = get_next_map_step("science", "больница")

        self.assertEqual(command, "В город")
        self.assertIn("затем иди на КПП", text)

    def test_region_screen_shows_access_reason_for_locked_zone(self):
        player = DummyPlayer(level=1, rank_tier=1, current_location_id="кпп")
        text = format_region_map(player, "forest")

        self.assertIn("закрыто", text)
        self.assertIn("уровень 3+", text)
        self.assertIn("Кнопка маршрута: Дорога на зараженный лес", text)

    def test_map_buttons_are_available_from_location_and_region_screen(self):
        location_keyboard = create_location_keyboard("город").get_keyboard()
        overview_from_service = create_map_overview_keyboard("больница").get_keyboard()
        region_keyboard = create_map_region_keyboard("science", "кпп").get_keyboard()

        self.assertIn("Карта", location_keyboard)
        self.assertIn("В город", overview_from_service)
        self.assertNotIn("КПП", overview_from_service)
        self.assertIn("Дорога на НИИ", region_keyboard)
        self.assertIn("Назад", region_keyboard)


if __name__ == "__main__":
    unittest.main()
