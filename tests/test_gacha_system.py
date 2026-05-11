import json
import unittest
from unittest.mock import call, patch

from game.gacha import banners, service
from game.gacha.assets import get_item_image_path
from game.gacha.event_items import (
    EVENT_ITEM_NAMES,
    GACHA_EVENT_ITEMS,
    format_event_outfit_passive_stats,
    get_event_item_lore,
    get_event_outfit_passive_profile,
    get_event_outfit_set_bonus,
    is_gacha_event_item,
    is_ssr_event_item,
)
from game.gacha.ui import (
    create_resonance_banner_keyboard,
    create_resonance_history_keyboard,
    create_resonance_keyboard,
    create_resonance_rates_keyboard,
    format_history,
    format_rates,
    format_resonance_menu,
    handle_resonance_command,
    _send_pull_result,
)
from handlers.inventory import build_item_details
from handlers.keyboards import create_location_keyboard
from infra import database
from game.item_pool import ITEMS_POOL
from game.weapon_progression import calc_weapon_attack, normalize_weapon_rank


class GachaSystemTest(unittest.TestCase):
    def test_core_costs_and_duration(self):
        self.assertEqual(banners.SINGLE_PULL_COST, 160)
        self.assertEqual(banners.TEN_PULL_COST, 1600)
        self.assertEqual(banners.BANNER_DURATION_DAYS, 20)
        self.assertEqual(banners.BANNER_PHASES_PER_PATCH, 2)
        self.assertEqual(banners.BANNER_PATCH_DURATION_DAYS, 40)

    def test_banner_time_left_is_formatted_to_seconds(self):
        self.assertEqual(service.format_seconds_left(2 * 86400 + 3 * 3600 + 4 * 60 + 5), "2д 03:04:05")

    def test_banner_cycle_auto_switches_second_phase_then_expires(self):
        settings = {}
        duration = banners.BANNER_DURATION_DAYS * 24 * 60 * 60

        def get_setting(key, default=None):
            return settings.get(key, default)

        def set_setting(key, value):
            settings[key] = value

        with patch("game.gacha.service.database.get_gacha_banner_snapshots", return_value={}), \
             patch("game.gacha.service.database.set_gacha_banner_snapshots"), \
             patch("game.gacha.service.database.get_game_setting", side_effect=get_setting), \
             patch("game.gacha.service.database.set_game_setting", side_effect=set_setting):
            first = service.ensure_banner_cycle(now_ts=1000)
            second = service.ensure_banner_cycle(now_ts=1000 + duration + 10)
            third = service.ensure_banner_cycle(now_ts=1000 + duration * 2 + 10)

        self.assertEqual(first["phase_number"], 1)
        self.assertFalse(first["expired"])
        self.assertEqual(second["phase_number"], 2)
        self.assertFalse(second["expired"])
        self.assertEqual(third["phase_number"], 2)
        self.assertTrue(third["expired"])

    def test_scheduled_banner_release_applies_exact_snapshot(self):
        settings = {
            service.SCHEDULED_BANNER_RELEASE_SETTING: json.dumps({
                "release_id": "patch_1",
                "start_ts": 2000,
            }),
        }
        snapshots = {}

        def get_setting(key, default=None):
            return settings.get(key, default)

        def set_setting(key, value):
            settings[key] = value

        def set_snapshots(cycle_start_ts, payload):
            snapshots[cycle_start_ts] = payload

        with patch("game.gacha.service.database.get_game_setting", side_effect=get_setting), \
             patch("game.gacha.service.database.set_game_setting", side_effect=set_setting), \
             patch("game.gacha.service.database.set_gacha_banner_snapshots", side_effect=set_snapshots), \
             patch("game.gacha.service.database.get_gacha_banner_snapshots", side_effect=lambda ts: snapshots.get(ts, {})):
            cycle = service.ensure_banner_cycle(now_ts=2001)
            active = service.get_active_banners(now_ts=2001)
            second_phase = service.get_active_banners(now_ts=2000 + banners.BANNER_DURATION_DAYS * 24 * 60 * 60 + 1)
            expired = service.get_active_banners(now_ts=2000 + banners.BANNER_PATCH_DURATION_DAYS * 24 * 60 * 60 + 1)

        self.assertEqual(cycle["start_ts"], 2000)
        self.assertEqual(settings[service.ACTIVE_BANNER_RELEASE_SETTING], "patch_1")
        self.assertEqual(settings[service.SCHEDULED_BANNER_RELEASE_SETTING], "")
        self.assertEqual(active["weapon"].featured_ssr, ("АК-74 «Резонанс»",))
        self.assertEqual(active["outfit"].featured_ssr, banners.SIGNAL_GUIDE_SET)
        self.assertEqual(second_phase["weapon"].featured_ssr, ("Винторез «Тихий Сигнал»",))
        self.assertEqual(second_phase["outfit"].featured_ssr, banners.RUPTURE_SEEKER_SET)
        self.assertEqual(expired, {})

    def test_active_banner_snapshot_is_saved_and_reused(self):
        settings = {}

        def get_setting(key, default=None):
            return settings.get(key, default)

        def set_setting(key, value):
            settings[key] = value

        with patch("game.gacha.service.database.get_gacha_banner_snapshots", return_value={}), \
             patch("game.gacha.service.database.set_gacha_banner_snapshots"), \
             patch("game.gacha.service.database.get_game_setting", side_effect=get_setting), \
             patch("game.gacha.service.database.set_game_setting", side_effect=set_setting):
            active = service.get_active_banners(now_ts=2000)
            snapshot_key = next(key for key in settings if key.startswith(service.BANNER_SNAPSHOT_SETTING_PREFIX))
            settings[snapshot_key] = json.dumps({
                "weapon": {
                    "id": "weapon",
                    "name": "Сохранённый оружейный баннер",
                    "featured_ssr": ["Нож «Осколок Разлома»"],
                    "off_ssr": ["АК-74 «Резонанс»"],
                    "sr_pool": [{"kind": "item", "name": "ПМ «Сбой»", "min_qty": 1, "max_qty": 1}],
                    "r_pool": [{"kind": "item", "name": "Бинт", "min_qty": 1, "max_qty": 1}],
                }
            }, ensure_ascii=False)
            reused = service.get_active_banners(now_ts=2000)

        self.assertEqual(active["weapon"].featured_ssr, ("АК-74 «Резонанс»",))
        self.assertEqual(reused["weapon"].name, "Сохранённый оружейный баннер")
        self.assertEqual(reused["weapon"].featured_ssr, ("Нож «Осколок Разлома»",))
        self.assertNotIn("АК-74 «Резонанс»", reused["weapon"].off_ssr)
        self.assertIn("АКС-74 «Серый Контур»", reused["weapon"].off_ssr)
        self.assertEqual(tuple(entry.name for entry in reused["weapon"].featured_sr), ("ПМ «Сбой»",))

    def test_second_phase_reuses_existing_items_as_rateups(self):
        phase = banners.build_phase_banners(1)

        self.assertEqual(phase["weapon"].featured_ssr, ("Винторез «Тихий Сигнал»",))
        self.assertNotIn("АК-74 «Резонанс»", phase["weapon"].off_ssr)
        self.assertIn("АКС-74 «Серый Контур»", phase["weapon"].off_ssr)
        self.assertEqual(phase["outfit"].featured_ssr, banners.RUPTURE_SEEKER_SET)
        self.assertIn("Маска «Искатель Разлома»", phase["outfit"].featured_ssr)
        self.assertNotIn("Плащ «Проводник Сигнала»", phase["outfit"].off_ssr)
        self.assertIn("Шлем «Глухой Контур»", phase["outfit"].off_ssr)

    def test_featured_ssr_exclusives_never_enter_offrate_pool(self):
        for phase_index in range(len(banners.BANNER_PHASES)):
            for banner in banners.build_phase_banners(phase_index).values():
                self.assertTrue(set(banner.off_ssr).isdisjoint(banners.FEATURED_SSR_EXCLUSIVE_NAMES))
                self.assertTrue(set(banner.off_ssr).isdisjoint(set(banner.featured_ssr)))

    def test_outfit_banner_uses_full_set_rateup_and_lower_pity(self):
        phase = banners.build_phase_banners(0)

        self.assertEqual(phase["outfit"].featured_ssr, banners.SIGNAL_GUIDE_SET)
        self.assertEqual(banners.get_ssr_hard_pity("outfit"), 60)
        self.assertEqual(banners.get_ssr_soft_pity_start("outfit"), 45)
        self.assertEqual(banners.get_ssr_hard_pity("weapon"), 80)

    def test_resonance_menu_shows_exact_banner_time_left(self):
        with patch("game.gacha.ui.get_exchange_wallet", return_value={"shards": 160, "dust": 0, "marks": 0, "weapon_tickets": 1, "outfit_tickets": 0}), \
             patch("game.gacha.ui.get_banner_time_left", return_value={"formatted": "19д 23:59:58", "phase_number": 1, "phases_per_patch": 2}), \
             patch("game.gacha.ui.get_banner_state", return_value={
                 "pity_ssr": 0,
                 "pity_sr": 0,
                 "featured_guaranteed": False,
        }):
            menu = format_resonance_menu(777)

        self.assertIn("До конца волны: 19д 23:59:58", menu)

    def test_resonance_main_keyboard_is_uncluttered_hud(self):
        keyboard = json.loads(create_resonance_keyboard().get_keyboard())
        payload = json.dumps(keyboard, ensure_ascii=False)

        self.assertFalse(keyboard["inline"])
        self.assertIn("Резонанс оружия", payload)
        self.assertIn("Резонанс снаряжения", payload)
        self.assertIn("Шансы оружия", payload)
        self.assertIn("Шансы снаряжения", payload)
        self.assertNotIn("Собрать", payload)
        self.assertNotIn("История резонанса", payload)
        self.assertNotIn('"label": "Резонанс Зоны"', payload)

    def test_resonance_main_keyboard_hides_banners_when_patch_expired(self):
        keyboard = json.loads(create_resonance_keyboard(active=False).get_keyboard())
        payload = json.dumps(keyboard, ensure_ascii=False)

        self.assertFalse(keyboard["inline"])
        self.assertNotIn("Резонанс оружия", payload)
        self.assertNotIn("Резонанс снаряжения", payload)
        self.assertNotIn("Шансы оружия", payload)
        self.assertIn("Назад", payload)

    def test_resonance_banner_keyboard_moves_pull_buttons_inside_banner(self):
        keyboard = json.loads(create_resonance_banner_keyboard("weapon").get_keyboard())
        first_row = keyboard["buttons"][0]
        labels = [button["action"]["label"] for button in first_row]
        second_row_labels = [button["action"]["label"] for button in keyboard["buttons"][1]]

        self.assertFalse(keyboard["inline"])
        self.assertEqual(labels, ["Оружие x1", "Оружие x10"])
        self.assertEqual(second_row_labels, ["История оружия"])
        self.assertNotIn("Шансы", json.dumps(keyboard, ensure_ascii=False))
        self.assertNotIn("Собрать", json.dumps(keyboard, ensure_ascii=False))

    def test_resonance_banner_back_text_returns_to_menu(self):
        class Player:
            current_location_id = "убежище"
            level = 1

        with patch("game.gacha.ui.show_resonance_menu") as show_menu:
            handled = handle_resonance_command(Player(), object(), 777, "Назад к резонансу")

        self.assertTrue(handled)
        show_menu.assert_called_once()

    def test_resonance_history_keyboard_has_hud_pagination_and_back(self):
        keyboard = json.loads(create_resonance_history_keyboard("weapon", page=0, total_pages=3).get_keyboard())
        page_payloads = [json.loads(button["action"]["payload"]) for button in keyboard["buttons"][0]]
        back_payload = json.loads(keyboard["buttons"][1][0]["action"]["payload"])

        self.assertEqual(page_payloads[0], {"command": "resonance_history", "banner": "weapon", "page": 2})
        self.assertEqual(page_payloads[1], {"command": "resonance_history", "banner": "weapon", "page": 0})
        self.assertEqual(page_payloads[2], {"command": "resonance_history", "banner": "weapon", "page": 1})
        self.assertEqual(back_payload, {"command": "resonance_back"})

    def test_resonance_rates_keyboard_has_hud_pagination_and_back(self):
        keyboard = json.loads(create_resonance_rates_keyboard("outfit", page=1, total_pages=3).get_keyboard())
        page_payloads = [json.loads(button["action"]["payload"]) for button in keyboard["buttons"][0]]
        back_payload = json.loads(keyboard["buttons"][1][0]["action"]["payload"])

        self.assertTrue(keyboard["inline"])
        self.assertEqual(page_payloads[0], {"command": "resonance_rates", "banner": "outfit", "page": 0})
        self.assertEqual(page_payloads[1], {"command": "resonance_rates", "banner": "outfit", "page": 1})
        self.assertEqual(page_payloads[2], {"command": "resonance_rates", "banner": "outfit", "page": 2})
        self.assertEqual(back_payload, {"command": "resonance_back"})

    def test_resonance_rates_pages_present_banner_items(self):
        rateup, page, total = format_rates("weapon", 0)
        sr_rateup, sr_page, _ = format_rates("weapon", 1)
        offrate, off_page, _ = format_rates("weapon", 2)
        details, details_page, _ = format_rates("weapon", 3)

        self.assertEqual((page, sr_page, off_page, details_page, total), (0, 1, 2, 3, 4))
        self.assertIn("RankUP SSR: АК-74 «Резонанс»", rateup)
        self.assertIn("Крит. шанс", rateup)
        self.assertIn("Rate-up при активном 50/50", rateup)
        self.assertIn("Rate-up SR: ПМ «Сбой»", sr_rateup)
        self.assertIn("SR средний шанс", sr_rateup)
        self.assertIn("АКС-74 «Серый Контур»", offrate)
        self.assertIn("СВД «Шум Предела»", offrate)
        self.assertIn("SR RATE-UP", details)
        self.assertIn("SR OFF-RATE", details)
        self.assertIn("SR ПУЛ", details)
        self.assertIn("R ПУЛ", details)

    def test_pull_history_is_separate_by_banner(self):
        storage = {}

        def get_state(_vk_id, key):
            return storage.get(key)

        def set_state(_vk_id, key, payload):
            storage[key] = payload

        with patch("game.gacha.service.database.get_runtime_state", side_effect=get_state), \
             patch("game.gacha.service.database.set_runtime_state", side_effect=set_state), \
             patch("game.gacha.service._now_ts", return_value=123456):
            service._record_pull_history(
                777,
                banners.WEAPON_BANNER,
                1,
                banners.SINGLE_PULL_COST,
                [service.PullReward("SSR", "АК-74 «Резонанс»")],
                0,
            )
            service._record_pull_history(
                777,
                banners.OUTFIT_BANNER,
                10,
                banners.TEN_PULL_COST,
                [service.PullReward("SR", "Куртка «Глухой эфир»")],
                160,
            )
            history = service.get_pull_history(777, "weapon")

        self.assertEqual(len(storage[service.RESONANCE_HISTORY_RUNTIME_KEY]["weapon"]), 1)
        self.assertEqual(len(storage[service.RESONANCE_HISTORY_RUNTIME_KEY]["outfit"]), 1)
        self.assertEqual(history["banner"].id, "weapon")
        self.assertEqual(history["items"][0]["rewards"][0]["name"], "АК-74 «Резонанс»")

    def test_format_history_uses_banner_specific_rows(self):
        with patch("game.gacha.ui.get_pull_history", return_value={
            "banner": banners.WEAPON_BANNER,
            "items": [{
                "ts": 123456,
                "count": 1,
                "best_rarity": "SSR",
                "rewards": [{"rarity": "SSR", "name": "АК-74 «Резонанс»", "quantity": 1}],
            }],
            "page": 0,
            "total_pages": 1,
            "total": 1,
        }):
            message, page, total_pages = format_history(777, "weapon", 0)

        self.assertEqual(page, 0)
        self.assertEqual(total_pages, 1)
        self.assertIn("ИСТОРИЯ: ОРУЖЕЙНЫЙ РЕЗОНАНС", message)
        self.assertIn("АК-74 «Резонанс»", message)

    def test_event_items_are_event_only(self):
        self.assertIn("АК-74 «Резонанс»", EVENT_ITEM_NAMES)
        self.assertTrue(is_gacha_event_item("Плащ «Проводник Сигнала»"))
        self.assertFalse(is_gacha_event_item("АК-74"))

    def test_event_items_have_no_normal_drop_profile(self):
        drop_chance, location_chances = database._resolve_item_drop_profile(
            "Плащ «Проводник Сигнала»",
            "armor",
        )

        self.assertEqual(drop_chance, 0)
        self.assertEqual(location_chances, {})

    def test_event_items_are_hidden_from_npc_shop_candidates(self):
        normal_item = {
            "id": 1,
            "name": "Кожаная куртка",
            "category": "armor",
            "rarity": "common",
            "price": 100,
        }
        event_item = {
            "id": 2,
            "name": "Плащ «Проводник Сигнала»",
            "category": "armor",
            "rarity": "legendary",
            "price": 0,
        }

        with patch("infra.database._get_cached_items", return_value=(
            {normal_item["name"]: normal_item, event_item["name"]: event_item},
            {"armor": [normal_item, event_item]},
            {},
        )):
            candidates = database._get_shop_candidates(database.NPC_MERCHANT_SOLDIER, category="armor")

        self.assertEqual([item["name"] for item in candidates], ["Кожаная куртка"])

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

        with patch("game.gacha.service.database.get_gacha_banner_stats", return_value={}), \
             patch("game.gacha.service.database.set_gacha_banner_stats"), \
             patch("game.gacha.service.database.get_game_setting", side_effect=get_setting), \
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
                if entry.kind == "item":
                    self.assertNotEqual(entry.name.lower(), "гильзы")

    def test_gacha_r_pool_contains_low_value_trash(self):
        trash_names = {item[0] for item in ITEMS_POOL if item[1] == "trash"}

        for banner in banners.BANNERS.values():
            r_item_names = {entry.name for entry in banner.r_pool if entry.kind == "item"}
            self.assertTrue(r_item_names & trash_names, banner.id)

    def test_ssr_event_items_have_lore_and_image_assets(self):
        self.assertTrue(is_ssr_event_item("АК-74 «Резонанс»"))
        self.assertIn("Эксклюзив Резонанса", get_event_item_lore("АК-74 «Резонанс»"))
        image_path = get_item_image_path("АК-74 «Резонанс»")
        self.assertIsNotNone(image_path)
        self.assertTrue(image_path.exists())

    def test_offrate_ssr_without_own_art_does_not_reuse_rateup_image(self):
        self.assertTrue(is_ssr_event_item("АКС-74 «Серый Контур»"))
        self.assertIsNone(get_item_image_path("АКС-74 «Серый Контур»"))
        self.assertIsNone(get_item_image_path("СВД «Шум Предела»"))
        self.assertIsNone(get_item_image_path("Шлем «Глухой Контур»"))

    def test_ssr_inspection_marks_exclusive(self):
        details = build_item_details({
            "name": "АК-74 «Резонанс»",
            "category": "weapons",
            "rarity": "legendary",
            "description": get_event_item_lore("АК-74 «Резонанс»"),
            "weight": 3.2,
            "attack": 205,
        })
        self.assertIn("Эксклюзив", details)
        self.assertIn("SSR Резонанса Зоны", details)
        self.assertIn("ДОП. СТАТ ОРУЖИЯ", details)
        self.assertIn("Стабилизатор резонанса", details)
        self.assertIn("Крит. шанс", details)

    def test_weapon_rateup_is_not_weaker_than_offrate_by_max_atk(self):
        by_name = {row[0]: row for row in GACHA_EVENT_ITEMS}

        def max_atk(item_name: str) -> int:
            row = by_name[item_name]
            item = {
                "name": row[0],
                "category": row[1],
                "attack": row[4],
                "base_attack": row[4],
                "rarity": row[8],
            }
            return calc_weapon_attack(item, 297, normalize_weapon_rank(None, item), 10)

        rateup_atk = max_atk("АК-74 «Резонанс»")
        offrate_atks = [max_atk(name) for name in banners.WEAPON_BANNER.off_ssr]

        self.assertGreaterEqual(rateup_atk, max(offrate_atks))

    def test_resonance_outfit_has_fixed_passives(self):
        cloak = get_event_outfit_passive_profile("Плащ «Проводник Сигнала»")
        gloves = get_event_outfit_passive_profile("Перчатки «Проводник Сигнала»")

        self.assertEqual(cloak["stats"]["find_chance"], 8)
        self.assertEqual(cloak["stats"]["rare_find_chance"], 4)
        self.assertEqual(gloves["stats"]["artifact_extract_bonus_pct"], 8)
        self.assertEqual(gloves["stats"]["precise_anomaly_shell_discount"], 1)
        self.assertIn("Извлечение артефакта +8%", format_event_outfit_passive_stats(gloves["stats"]))

    def test_full_signal_guide_set_bonus_exists(self):
        bonuses = get_event_outfit_set_bonus(banners.SIGNAL_GUIDE_SET)

        self.assertEqual(len(bonuses), 1)
        self.assertEqual(bonuses[0]["name"], "Полный комплект: Проводник Сигнала")
        self.assertEqual(bonuses[0]["stats"]["rare_find_chance"], 3)

    def test_ssr_outfit_inspection_shows_passive(self):
        details = build_item_details({
            "name": "Плащ «Проводник Сигнала»",
            "category": "armor",
            "rarity": "legendary",
            "description": get_event_item_lore("Плащ «Проводник Сигнала»"),
            "weight": 8.4,
            "defense": 92,
        })

        self.assertIn("ПАССИВ СНАРЯЖЕНИЯ", details)
        self.assertIn("Полевой проводник", details)
        self.assertIn("Шанс находок +8%", details)

    def test_event_items_not_tradable_on_market(self):
        item = {"name": "АК-74 «Резонанс»", "category": "weapons"}
        self.assertFalse(database._is_market_item_tradable(item))

    def test_shelter_keyboard_has_resonance_entry(self):
        payload = create_location_keyboard("убежище").get_keyboard()
        self.assertIn("Резонанс Зоны", payload)

    def test_availability_requires_only_global_toggle(self):
        with patch("game.gacha.service.is_resonance_enabled", return_value=True):
            self.assertTrue(service.is_resonance_available(777))

        with patch("game.gacha.service.is_resonance_enabled", return_value=False):
            self.assertFalse(service.is_resonance_available(777))

    def test_public_launch_enables_resonance_once(self):
        settings = {}

        def get_setting(key, default=None):
            return settings.get(key, default)

        def set_setting(key, value):
            settings[key] = value

        with patch("game.gacha.service.database.get_game_setting", side_effect=get_setting), \
             patch("game.gacha.service.database.set_game_setting", side_effect=set_setting), \
             patch("game.gacha.service._now_ts", return_value=1000):
            service.ensure_resonance_public_launch()

        self.assertEqual(settings[banners.GACHA_ENABLED_SETTING], "1")
        self.assertEqual(settings[service.PUBLIC_LAUNCH_SETTING], "1")

    def test_resonance_launch_notice_is_lore_short_and_once(self):
        settings = {}

        def get_setting(key, default=None):
            return settings.get(key, default)

        def set_setting(key, value):
            settings[key] = value

        class Messages:
            def __init__(self):
                self.sent = []

            def send(self, **kwargs):
                self.sent.append(kwargs)
                return len(self.sent)

        class Vk:
            def __init__(self):
                self.messages = Messages()

        vk = Vk()
        runtime = {}

        def get_runtime(vk_id, key):
            return runtime.get((vk_id, key))

        def set_runtime(vk_id, key, payload):
            runtime[(vk_id, key)] = payload

        with patch("game.gacha.service.database.get_game_setting", side_effect=get_setting), \
             patch("game.gacha.service.database.set_game_setting", side_effect=set_setting), \
             patch("game.gacha.service.database.get_runtime_state", side_effect=get_runtime), \
             patch("game.gacha.service.database.set_runtime_state", side_effect=set_runtime), \
             patch("game.gacha.service.add_signal_shards", side_effect=[1760, 1600]) as add_shards, \
             patch("game.gacha.service.database.get_all_active_players", return_value=[{"vk_id": 10}, {"vk_id": 20}]):
            result = service.send_resonance_launch_notice_once(vk)
            second = service.send_resonance_launch_notice_once(vk)

        self.assertEqual(result, {"sent": 2, "errors": 0, "rewarded": 2, "reward_errors": 0, "skipped": False})
        self.assertEqual(second, {"sent": 0, "errors": 0, "rewarded": 0, "reward_errors": 0, "skipped": True})
        self.assertEqual(settings[service.PUBLIC_LAUNCH_NOTICE_SETTING], "1")
        self.assertEqual(settings[service.PUBLIC_LAUNCH_REWARD_SETTING], "1")
        add_shards.assert_has_calls([
            call(10, service.PUBLIC_LAUNCH_REWARD_SHARDS, source="public_resonance_launch", details={"amount": service.PUBLIC_LAUNCH_REWARD_SHARDS, "notice": service.PUBLIC_LAUNCH_NOTICE_SETTING}),
            call(20, service.PUBLIC_LAUNCH_REWARD_SHARDS, source="public_resonance_launch", details={"amount": service.PUBLIC_LAUNCH_REWARD_SHARDS, "notice": service.PUBLIC_LAUNCH_NOTICE_SETTING}),
        ])
        self.assertEqual(len(vk.messages.sent), 2)
        message = vk.messages.sent[0]["message"]
        self.assertIn("ГОРОДСКОЕ ОПОВЕЩЕНИЕ", message)
        self.assertIn("сдвига фона", message)
        self.assertIn("остаточные слепки вещей", message)
        self.assertIn("самовольный запуск", message.lower())
        self.assertIn("запечатанные отклики", message)
        self.assertIn("осколков сигнала", message)
        self.assertIn("Барыги на Чёрном рынке", message)
        self.assertIn("1600 осколков сигнала", message)
        self.assertIn("поверх уже найденных", message)
        self.assertIn("Убежища: Резонанс", message)

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
             patch("game.gacha.service.database.remove_item_from_inventory", return_value=True), \
             patch("game.gacha.service.database.add_shells", return_value=(True, "")):
            result = service.perform_pulls(777, "weapon", 1)

        self.assertTrue(result["success"])
        self.assertEqual(result["shards_left"], 0)
        self.assertEqual(result["ticket"], "Оружейный отклик")
        self.assertEqual(result["converted_tickets"], 1)
        self.assertEqual(result["rewards"][0].rarity, "SSR")
        self.assertEqual(result["state"]["pity_ssr"], 0)
        add_storage_mock.assert_not_called()
        add_inventory_mock.assert_has_calls([
            call(777, "Оружейный отклик", 1),
            call(777, "АК-74 «Резонанс»", 1),
        ])

    def test_non_duplicate_ssr_goes_to_inventory(self):
        reward = service.PullReward("SSR", "АК-74 «Резонанс»")
        with patch("game.gacha.service.database.get_user_inventory", return_value=[]), \
             patch("game.gacha.service.database.get_user_storage", return_value=[]), \
             patch("game.gacha.service.database.get_user_by_vk", return_value={}), \
             patch("game.gacha.service.database.add_item_to_inventory", return_value=True) as add_inventory_mock, \
             patch("game.gacha.service.database.add_item_to_storage", return_value=True) as add_storage_mock:
            granted = service._grant_reward(777, reward)

        self.assertFalse(granted.duplicate)
        add_inventory_mock.assert_called_once_with(777, "АК-74 «Резонанс»", 1)
        add_storage_mock.assert_not_called()

    def test_public_player_reaches_pull_cost_check_without_admin_gate(self):
        with patch("game.gacha.service.is_resonance_enabled", return_value=True), \
             patch("game.gacha.service.database.is_user_admin", return_value=False), \
             patch("game.gacha.service.get_banner", return_value=banners.WEAPON_BANNER), \
             patch("game.gacha.service._ensure_pull_tickets", return_value={"success": False, "message": "Не хватает откликов."}):
            result = service.perform_pulls(777, "weapon", 1)

        self.assertFalse(result["success"])
        self.assertIn("Не хватает откликов", result["message"])

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
        add_shards_mock.assert_called_once()
        self.assertEqual(add_shards_mock.call_args.args[:2], (777, 800))
        self.assertEqual(add_shards_mock.call_args.kwargs["source"], "duplicate_ssr")
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
        add_shards_mock.assert_called_once()
        self.assertEqual(add_shards_mock.call_args.args[:2], (777, 800))
        self.assertEqual(add_shards_mock.call_args.kwargs["source"], "duplicate_ssr")
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
             patch("game.gacha.service.database.add_item_to_storage", return_value=True), \
             patch("game.gacha.service.database.add_item_to_inventory", return_value=True), \
             patch("game.gacha.service.database.remove_item_from_inventory", return_value=True):
            result = service.perform_pulls(777, "weapon", 1)

        self.assertTrue(result["success"])
        self.assertEqual(result["shards_left"], 800)
        self.assertEqual(result["rewards"][0].name, "Осколки сигнала")
        self.assertEqual(result["rewards"][0].quantity, 800)

    def test_sr_rateup_guarantee_after_offrate_sr(self):
        state = {"pity_ssr": 0, "pity_sr": 0, "featured_sr_guaranteed": False}
        with patch("game.gacha.service.random.random", return_value=0.9), \
             patch("game.gacha.service.random.choice", side_effect=lambda seq: seq[0]):
            first = service._roll_sr(banners.WEAPON_BANNER, state)

        self.assertEqual(first.name, "ИЖ-27 «Глухой Отклик»")
        self.assertTrue(first.sr_rateup_lost)
        self.assertTrue(state["featured_sr_guaranteed"])

        with patch("game.gacha.service.random.choice", side_effect=lambda seq: seq[0]):
            second = service._roll_sr(banners.WEAPON_BANNER, state)

        self.assertEqual(second.name, "ПМ «Сбой»")
        self.assertTrue(second.sr_featured)
        self.assertTrue(second.sr_guaranteed)
        self.assertFalse(state["featured_sr_guaranteed"])

    def test_outfit_featured_ssr_excludes_owned_set_pieces(self):
        with patch("game.gacha.service._has_item", side_effect=lambda _vk_id, name: name == "Плащ «Проводник Сигнала»"):
            candidates = service._owned_featured_candidates(777, banners.OUTFIT_BANNER)

        self.assertNotIn("Плащ «Проводник Сигнала»", candidates)
        self.assertIn("Маска «Проводник Сигнала»", candidates)
        self.assertEqual(len(candidates), 3)

    def test_outfit_featured_ssr_removed_from_same_ten_pull_candidates(self):
        state = {
            "pity_ssr": 1,
            "pity_sr": 0,
            "featured_guaranteed": True,
            "featured_candidates": ("Плащ «Проводник Сигнала»", "Маска «Проводник Сигнала»"),
        }

        with patch("game.gacha.service.random.choice", side_effect=lambda seq: seq[0]):
            first = service._roll_ssr(banners.OUTFIT_BANNER, state)
            state["featured_guaranteed"] = True
            second = service._roll_ssr(banners.OUTFIT_BANNER, state)

        self.assertEqual(first.name, "Плащ «Проводник Сигнала»")
        self.assertEqual(second.name, "Маска «Проводник Сигнала»")
        self.assertEqual(state["featured_candidates"], ())

    def test_ten_pull_sends_each_ssr_as_separate_showcase(self):
        class Vk:
            pass

        sent = []
        result = {
            "success": True,
            "banner": banners.WEAPON_BANNER,
            "count": 10,
            "cost": 10,
            "ticket": "Оружейный отклик",
            "tickets_left": 0,
            "converted_tickets": 0,
            "shards_left": 0,
            "exchange_reward": {"dust": 150, "dust_balance": 150, "marks": 11, "marks_balance": 11},
            "rewards": [
                service.PullReward("R", "Бинт"),
                service.PullReward("SSR", "АК-74 «Резонанс»", featured=True),
                service.PullReward("SR", "ПМ «Сбой»"),
                service.PullReward("SSR", "АКС-74 «Серый Контур»", fifty_fifty_lost=True),
            ],
            "state": {
                "pity_ssr": 0,
                "pity_sr": 3,
                "featured_guaranteed": True,
                "featured_sr_guaranteed": False,
            },
        }

        with patch("game.gacha.ui.vk_messages.send", side_effect=lambda _vk, **kwargs: sent.append(kwargs)), \
             patch("game.gacha.ui.get_banner_time_left", return_value={"formatted": "1д 00:00:00"}), \
             patch("game.gacha.ui.upload_item_image", side_effect=lambda _vk, _user_id, item: f"photo:{item}"):
            _send_pull_result(Vk(), 777, "weapon", result)

        self.assertEqual(len(sent), 3)
        self.assertIn("Откликов: x10", sent[0]["message"])
        self.assertIsNone(sent[0].get("attachment"))
        self.assertIn("1/2 из отклика x10", sent[1]["message"])
        self.assertIn("АК-74 «Резонанс»", sent[1]["message"])
        self.assertEqual(sent[1]["attachment"], "photo:АК-74 «Резонанс»")
        self.assertIn("2/2 из отклика x10", sent[2]["message"])
        self.assertIn("АКС-74 «Серый Контур»", sent[2]["message"])

    def test_daily_quest_shards_scale_but_stay_below_single_pull(self):
        with patch("game.gacha.service.add_signal_shards", return_value=500) as add_shards:
            reward = service.grant_daily_quest_shards(777, streak=7)

        self.assertEqual(reward["granted"], 84)
        add_shards.assert_called_once()
        self.assertEqual(add_shards.call_args.args[:2], (777, 84))
        self.assertEqual(add_shards.call_args.kwargs["source"], "daily_quest")

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
