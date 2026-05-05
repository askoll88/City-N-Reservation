import unittest
from unittest.mock import patch

from game.gacha import banners, service
from game.gacha.assets import get_item_image_path
from game.gacha.event_items import EVENT_ITEM_NAMES, get_event_item_lore, is_gacha_event_item, is_ssr_event_item
from handlers.inventory import build_item_details
from handlers.keyboards import create_location_keyboard
from infra import database


class GachaSystemTest(unittest.TestCase):
    def test_core_costs_and_duration(self):
        self.assertEqual(banners.SINGLE_PULL_COST, 160)
        self.assertEqual(banners.TEN_PULL_COST, 1600)
        self.assertEqual(banners.BANNER_DURATION_DAYS, 20)

    def test_event_items_are_event_only(self):
        self.assertIn("АК-74 «Резонанс»", EVENT_ITEM_NAMES)
        self.assertTrue(is_gacha_event_item("Плащ «Проводник Сигнала»"))
        self.assertFalse(is_gacha_event_item("АК-74"))

    def test_ssr_event_items_have_lore_and_image_assets(self):
        self.assertTrue(is_ssr_event_item("АК-74 «Резонанс»"))
        self.assertIn("Эксклюзив Резонанса", get_event_item_lore("АК-74 «Резонанс»"))
        image_path = get_item_image_path("АК-74 «Резонанс»")
        self.assertIsNotNone(image_path)
        self.assertTrue(image_path.exists())

    def test_ssr_inspection_marks_exclusive(self):
        details = build_item_details({
            "name": "АК-74 «Резонанс»",
            "category": "weapons",
            "rarity": "legendary",
            "description": get_event_item_lore("АК-74 «Резонанс»"),
            "weight": 3.2,
            "attack": 145,
        })
        self.assertIn("Эксклюзив", details)
        self.assertIn("SSR Резонанса Зоны", details)

    def test_event_items_not_tradable_on_market(self):
        item = {"name": "АК-74 «Резонанс»", "category": "weapons"}
        self.assertFalse(database._is_market_item_tradable(item))

    def test_shelter_keyboard_has_resonance_entry(self):
        payload = create_location_keyboard("убежище").get_keyboard()
        self.assertIn("Резонанс Зоны", payload)

    def test_availability_requires_toggle_and_admin(self):
        with patch("game.gacha.service.is_resonance_enabled", return_value=True), \
             patch("game.gacha.service.database.is_user_admin", return_value=False):
            self.assertFalse(service.is_resonance_available(777))

        with patch("game.gacha.service.is_resonance_enabled", return_value=True), \
             patch("game.gacha.service.database.is_user_admin", return_value=True):
            self.assertTrue(service.is_resonance_available(777))

    def test_hard_pity_forces_ssr_and_spends_shards(self):
        flags = {
            banners.SIGNAL_SHARDS_FLAG: 160,
            "resonance_weapon_pity_ssr": 79,
            "resonance_weapon_pity_sr": 0,
            "resonance_weapon_featured_guaranteed": 1,
        }

        def get_flag(_vk_id, name, default=0):
            return flags.get(name, default)

        def set_flag(_vk_id, name, value):
            flags[name] = value

        with patch("game.gacha.service.is_resonance_enabled", return_value=True), \
             patch("game.gacha.service.database.is_user_admin", return_value=True), \
             patch("game.gacha.service.database.get_user_flag", side_effect=get_flag), \
             patch("game.gacha.service.database.set_user_flag", side_effect=set_flag), \
             patch("game.gacha.service.database.get_user_inventory", return_value=[]), \
             patch("game.gacha.service.database.add_item_to_inventory", return_value=True), \
             patch("game.gacha.service.database.add_shells", return_value=(True, "")):
            result = service.perform_pulls(777, "weapon", 1)

        self.assertTrue(result["success"])
        self.assertEqual(result["shards_left"], 0)
        self.assertEqual(result["rewards"][0].rarity, "SSR")
        self.assertEqual(result["state"]["pity_ssr"], 0)


if __name__ == "__main__":
    unittest.main()
