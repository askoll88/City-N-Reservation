import unittest
from unittest.mock import patch

from game.gacha import banners, service
from game.gacha.assets import get_item_image_path
from game.gacha.event_items import EVENT_ITEM_NAMES, get_event_item_lore, is_gacha_event_item, is_ssr_event_item
from game.gacha.ui import format_resonance_menu
from handlers.inventory import build_item_details
from handlers.keyboards import create_location_keyboard
from infra import database


class GachaSystemTest(unittest.TestCase):
    def test_core_costs_and_duration(self):
        self.assertEqual(banners.SINGLE_PULL_COST, 160)
        self.assertEqual(banners.TEN_PULL_COST, 1600)
        self.assertEqual(banners.BANNER_DURATION_DAYS, 20)

    def test_banner_time_left_is_formatted_to_seconds(self):
        self.assertEqual(service.format_seconds_left(2 * 86400 + 3 * 3600 + 4 * 60 + 5), "2д 03:04:05")

    def test_resonance_menu_shows_exact_banner_time_left(self):
        with patch("game.gacha.ui.get_signal_shards", return_value=160), \
             patch("game.gacha.ui.get_banner_time_left", return_value={"formatted": "19д 23:59:58"}), \
             patch("game.gacha.ui.get_banner_state", return_value={
                 "pity_ssr": 0,
                 "pity_sr": 0,
                 "featured_guaranteed": False,
             }):
            menu = format_resonance_menu(777)

        self.assertIn("До конца баннера: 19д 23:59:58", menu)

    def test_event_items_are_event_only(self):
        self.assertIn("АК-74 «Резонанс»", EVENT_ITEM_NAMES)
        self.assertTrue(is_gacha_event_item("Плащ «Проводник Сигнала»"))
        self.assertFalse(is_gacha_event_item("АК-74"))

    def test_current_banner_stats_are_anonymous_aggregates(self):
        settings = {}

        def get_setting(key, default=None):
            return settings.get(key, default)

        def set_setting(key, value):
            settings[key] = value

        rewards = [
            service.PullReward("SSR", "АК-74 «Резонанс»", featured=True, pity_count=20),
            service.PullReward("SSR", "Винторез «Тихий Сигнал»", fifty_fifty_lost=True, pity_count=70),
            service.PullReward("R", "Бинт"),
        ]

        with patch("game.gacha.service.database.get_game_setting", side_effect=get_setting), \
             patch("game.gacha.service.database.set_game_setting", side_effect=set_setting), \
             patch("game.gacha.service._now_ts", return_value=1000):
            service._record_banner_stats(banners.WEAPON_BANNER, rewards)
            stats = service.get_current_banner_stats()

        weapon_stats = next(row for row in stats["banners"] if row["banner"].id == "weapon")
        self.assertEqual(weapon_stats["stats"]["pulls"], 3)
        self.assertEqual(weapon_stats["stats"]["rateup_ssr"], 1)
        self.assertEqual(weapon_stats["stats"]["fifty_fifty_losses"], 1)
        self.assertEqual(weapon_stats["average_pity"], 45.0)

    def test_gacha_banners_do_not_drop_shells(self):
        for banner in banners.BANNERS.values():
            for entry in [*banner.r_pool, *banner.sr_pool]:
                self.assertNotEqual(entry.kind, "shells")
                self.assertNotEqual(entry.name.lower(), "гильзы")

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
        self.assertIn("ДОП. СТАТ ОРУЖИЯ", details)
        self.assertIn("Стабилизатор резонанса", details)
        self.assertIn("Крит. шанс", details)

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
             patch("game.gacha.service.database.get_user_storage", return_value=[]), \
             patch("game.gacha.service.database.get_user_by_vk", return_value={}), \
             patch("game.gacha.service.database.add_item_to_storage", return_value=True) as add_storage_mock, \
             patch("game.gacha.service.database.add_item_to_inventory", return_value=True) as add_inventory_mock, \
             patch("game.gacha.service.database.add_shells", return_value=(True, "")):
            result = service.perform_pulls(777, "weapon", 1)

        self.assertTrue(result["success"])
        self.assertEqual(result["shards_left"], 0)
        self.assertEqual(result["rewards"][0].rarity, "SSR")
        self.assertEqual(result["state"]["pity_ssr"], 0)
        add_storage_mock.assert_called_once()
        add_inventory_mock.assert_not_called()

    def test_duplicate_ssr_checks_storage_and_compensation_goes_to_signal_shards(self):
        reward = service.PullReward("SSR", "АК-74 «Резонанс»")
        with patch("game.gacha.service.database.get_user_inventory", return_value=[]), \
             patch("game.gacha.service.database.get_user_storage", return_value=[{"name": "АК-74 «Резонанс»"}]), \
             patch("game.gacha.service.database.get_user_by_vk", return_value={}), \
             patch("game.gacha.service.add_signal_shards", return_value=800) as add_shards_mock, \
             patch("game.gacha.service.database.add_item_to_storage", return_value=True) as add_storage_mock:
            granted = service._grant_reward(777, reward)

        self.assertTrue(granted.duplicate)
        self.assertEqual(granted.kind, "currency")
        self.assertEqual(granted.name, "Осколки сигнала")
        self.assertEqual(granted.quantity, 800)
        self.assertEqual(granted.source_name, "АК-74 «Резонанс»")
        add_shards_mock.assert_called_once_with(777, 800)
        add_storage_mock.assert_not_called()

    def test_duplicate_ssr_checks_equipped_items(self):
        reward = service.PullReward("SSR", "АК-74 «Резонанс»")
        with patch("game.gacha.service.database.get_user_inventory", return_value=[]), \
             patch("game.gacha.service.database.get_user_storage", return_value=[]), \
             patch("game.gacha.service.database.get_user_by_vk", return_value={"equipped_weapon": "АК-74 «Резонанс»"}), \
             patch("game.gacha.service.add_signal_shards", return_value=800) as add_shards_mock, \
             patch("game.gacha.service.database.add_item_to_storage", return_value=True) as add_storage_mock:
            granted = service._grant_reward(777, reward)

        self.assertTrue(granted.duplicate)
        add_shards_mock.assert_called_once_with(777, 800)
        add_storage_mock.assert_not_called()

    def test_duplicate_ssr_updates_pull_result_shards_left(self):
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
             patch("game.gacha.service.database.get_user_inventory", return_value=[{"name": "АК-74 «Резонанс»"}]), \
             patch("game.gacha.service.database.get_user_storage", return_value=[]), \
             patch("game.gacha.service.database.get_user_by_vk", return_value={}), \
             patch("game.gacha.service.database.add_item_to_storage", return_value=True):
            result = service.perform_pulls(777, "weapon", 1)

        self.assertTrue(result["success"])
        self.assertEqual(result["shards_left"], 800)
        self.assertEqual(result["rewards"][0].name, "Осколки сигнала")
        self.assertEqual(result["rewards"][0].quantity, 800)

    def test_daily_quest_shards_scale_but_stay_below_single_pull(self):
        with patch("game.gacha.service.add_signal_shards", return_value=500) as add_shards:
            reward = service.grant_daily_quest_shards(777, streak=7)

        self.assertEqual(reward["granted"], 84)
        add_shards.assert_called_once_with(777, 84)

    def test_combat_shards_only_for_hard_fights(self):
        with patch("game.gacha.service.get_signal_shards", return_value=0):
            easy = service.grant_combat_shards(777, enemy_level=5, reward_mult=1.0, player_level=5)

        self.assertEqual(easy["granted"], 0)

    def test_capped_signal_shards_respect_daily_source_limit(self):
        flags = {
            "resonance_event_shards_day": service._today_ordinal(),
            "resonance_event_shards_used": 75,
            banners.SIGNAL_SHARDS_FLAG: 1000,
        }

        def get_flag(_vk_id, name, default=0):
            return flags.get(name, default)

        def set_flag(_vk_id, name, value):
            flags[name] = value

        with patch("game.gacha.service.database.get_user_flag", side_effect=get_flag), \
             patch("game.gacha.service.database.set_user_flag", side_effect=set_flag):
            reward = service.add_signal_shards_capped(777, 20, "event", 80)

        self.assertEqual(reward["granted"], 5)
        self.assertEqual(flags[banners.SIGNAL_SHARDS_FLAG], 1005)
        self.assertEqual(flags["resonance_event_shards_used"], 80)

    def test_event_shards_reward_positive_event_result(self):
        with patch("game.gacha.service.add_signal_shards_capped", return_value={"granted": 16, "balance": 16, "cap": 80, "used": 16}) as capped:
            reward = service.grant_event_shards(
                777,
                {"type": "reward"},
                {"message": "Ты нашёл тайник. +100 руб.", "next_stage": None, "is_final": True},
            )

        self.assertEqual(reward["granted"], 16)
        capped.assert_called_once()


if __name__ == "__main__":
    unittest.main()
