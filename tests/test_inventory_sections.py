import importlib
import json
import sys
import types
import unittest
from unittest.mock import Mock, patch

from handlers.keyboards import create_inventory_hud_keyboard, create_inventory_keyboard, create_shop_hud_keyboard
from infra.state_manager import invalidate_edit_targets


class DummyKeyboard:
    def get_keyboard(self):
        return "{}"


class DummyVKMessages:
    def __init__(self):
        self.sent = []
        self.edited = []

    def send(self, **kwargs):
        self.sent.append(kwargs)
        return len(self.sent)

    def edit(self, **kwargs):
        self.edited.append(kwargs)
        return 1

class DummyVK:
    def __init__(self):
        self.messages = DummyVKMessages()


class DummyInventory:
    def __init__(self):
        self.weapons = [{"name": "ПМ", "quantity": 1, "attack": 10, "weight": 1.0}]
        self.armor = [{"name": "Куртка", "quantity": 1, "defense": 5, "weight": 2.0}]
        self.backpacks = [{"name": "Рюкзак", "quantity": 1, "backpack_bonus": 10, "weight": 1.5}]
        self.artifacts = [{"name": "Медуза", "quantity": 1, "weight": 0.5}]
        self.shells_bags = []
        self.trash = [{"name": "Комок ржавой стружки", "quantity": 1, "weight": 0.06, "price": 2}]
        self.other = [{"name": "Бинт", "quantity": 2, "weight": 0.1}]
        self.total_weight = 4.6

    def reload(self):
        pass


class DummyPlayer:
    def __init__(self):
        self.inventory_section = None
        self.inventory = DummyInventory()
        self.equipped_weapon = "ПМ"
        self.equipped_armor = None
        self.equipped_armor_head = None
        self.equipped_armor_body = "Куртка"
        self.equipped_armor_legs = None
        self.equipped_armor_hands = None
        self.equipped_armor_feet = None
        self.equipped_backpack = "Рюкзак"
        self.equipped_device = None
        self.equipped_artifacts = []
        self.artifact_slots = 3
        self.max_weight = 30
        self.money = 100
        self.level = 1
        self.current_location_id = "город"

    @property
    def sell_bonus(self):
        return 0


class InventorySectionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Фейковый database и main, чтобы не тащить внешние зависимости
        cls.fake_db = types.ModuleType("database")
        cls.fake_db.update_user_stats = Mock()
        cls.fake_db.get_item_by_name = Mock(return_value={})
        sys.modules["database"] = cls.fake_db

        fake_main = types.ModuleType("main")
        fake_main.create_inventory_keyboard = lambda *args, **kwargs: DummyKeyboard()
        fake_main.create_location_keyboard = lambda *args, **kwargs: DummyKeyboard()
        sys.modules["main"] = fake_main

        cls.inventory_module = importlib.import_module("handlers.inventory")

    def setUp(self):
        self.fake_db.update_user_stats.reset_mock()
        self.vk = DummyVK()
        self.player = DummyPlayer()

    def test_show_weapons_sets_section_in_memory_only(self):
        self.inventory_module.show_weapons(self.player, self.vk, user_id=1)
        self.assertEqual(self.player.inventory_section, "weapons")
        self.fake_db.update_user_stats.assert_not_called()

    def test_show_armor_sets_section_in_memory_only(self):
        self.inventory_module.show_armor(self.player, self.vk, user_id=1)
        self.assertEqual(self.player.inventory_section, "armor")
        self.fake_db.update_user_stats.assert_not_called()

    def test_show_backpacks_sets_section_in_memory_only(self):
        self.inventory_module.show_backpacks(self.player, self.vk, user_id=1)
        self.assertEqual(self.player.inventory_section, "backpacks")
        self.fake_db.update_user_stats.assert_not_called()

    def test_show_artifacts_sets_section_in_memory_only(self):
        self.inventory_module.show_artifacts(self.player, self.vk, user_id=1)
        self.assertEqual(self.player.inventory_section, "artifacts")
        self.fake_db.update_user_stats.assert_not_called()

    def test_artifact_bonus_text_uses_shared_bonus_table(self):
        text = self.inventory_module._artifact_bonus_text({"name": "Кристальная колючка"})

        self.assertIn("крит +10%", text)
        self.assertIn("защита +25", text)
        self.assertIn("уклон +15%", text)
        self.assertNotIn("без бонусов", text)

    def test_show_other_sets_section_in_memory_only(self):
        self.inventory_module.show_other(self.player, self.vk, user_id=1)
        self.assertEqual(self.player.inventory_section, "other")
        self.fake_db.update_user_stats.assert_not_called()

    def test_show_trash_sets_section_in_memory_only(self):
        self.inventory_module.show_trash(self.player, self.vk, user_id=1)
        self.assertEqual(self.player.inventory_section, "trash")
        self.fake_db.update_user_stats.assert_not_called()
        output = (self.vk.messages.sent or self.vk.messages.edited)[0]["message"]
        self.assertIn("ИНВЕНТАРЬ: ХЛАМ", output)

    def test_legendary_drop_requires_confirmation(self):
        self.player.inventory.other = [{"name": "АК-74 «Резонанс»", "quantity": 1, "weight": 3.2, "item_rank": "legendary"}]

        with patch.object(self.inventory_module.database, "get_user_by_vk", return_value={}), \
             patch.object(self.inventory_module.database, "get_runtime_state", return_value={}), \
             patch.object(self.inventory_module.database, "set_runtime_state") as set_state, \
             patch.object(self.inventory_module.database, "drop_item_from_inventory") as drop_item:
            self.inventory_module.handle_drop_item(self.player, "АК-74 «Резонанс»", self.vk, user_id=1)

        drop_item.assert_not_called()
        set_state.assert_called()
        self.assertIn("легендарный предмет", self.vk.messages.sent[-1]["message"])
        self.assertIn("подтвердить выброс", self.vk.messages.sent[-1]["message"])

    def test_legendary_drop_confirm_command_drops_pending_item(self):
        self.player.inventory.other = [{"name": "АК-74 «Резонанс»", "quantity": 1, "weight": 3.2, "item_rank": "legendary"}]

        with patch.object(self.inventory_module.database, "get_user_by_vk", return_value={}), \
             patch.object(self.inventory_module.database, "get_runtime_state", return_value={
                 "item_name": "АК-74 «Резонанс»",
                 "expires_at": 9999999999,
             }), \
             patch.object(self.inventory_module.database, "set_runtime_state"), \
             patch.object(self.inventory_module.database, "drop_item_from_inventory", return_value={
                 "success": True,
                 "message": "✅ Ты выбросил 1 шт. 'АК-74 «Резонанс»'",
             }) as drop_item:
            handled = self.inventory_module.handle_confirm_drop(self.player, self.vk, user_id=1)

        self.assertTrue(handled)
        drop_item.assert_called_once_with(1, "АК-74 «Резонанс»", 1)
        self.assertIn("Ты выбросил", self.vk.messages.sent[-1]["message"])

    def test_handle_sell_all_trash_uses_single_database_transaction(self):
        self.inventory_module.database.NPC_MERCHANT_TRADER = "trader"
        self.inventory_module.database.sell_all_trash_transaction = Mock(return_value={
            "success": True,
            "message": "Барыга забрал весь хлам: 3 шт. за 7 руб.",
            "remaining_money": 107,
        })

        with patch("handlers.quests.track_quest_shop_sell"):
            self.inventory_module.handle_sell_all_trash(self.player, self.vk, user_id=1)

        self.inventory_module.database.sell_all_trash_transaction.assert_called_once_with(
            1,
            sell_bonus_pct=0,
            merchant_id="trader",
        )
        self.assertEqual(self.player.money, 107)
        self.assertIn("Барыга забрал весь хлам", self.vk.messages.sent[0]["message"])

    def test_handle_use_item_equips_endgame_detector_without_detector_word(self):
        self.player.inventory.other = [{"name": "Око Зоны", "quantity": 1, "weight": 0.3}]

        def equip_device(name):
            self.player.equipped_device = name
            return True, f"Надето устройство: {name}"

        self.player.equip_device = equip_device

        self.inventory_module.handle_use_item(self.player, "Око Зоны", self.vk, user_id=1)

        self.assertEqual(self.player.equipped_device, "Око Зоны")
        self.assertIn("Надето устройство: Око Зоны", self.vk.messages.sent[0]["message"])

    def test_handle_equip_artifact_by_name_accepts_no_yo_input(self):
        self.player.inventory.artifacts = [{"name": "Плёнка", "quantity": 1, "weight": 0.1}]
        self.player._artifact_bonuses = {"dodge": 6, "radiation": -3}
        self.player.health = 100
        self.player.max_health = 100
        self.player.reload = lambda: None
        self.player._recalculate_max_weight = lambda: None

        with patch.object(self.inventory_module.database, "equip_artifact", return_value={"success": True, "message": "✅ Артефакт Плёнка экипирован!"}) as equip_artifact, \
             patch.object(self.inventory_module.database, "update_user_stats"):
            handled = self.inventory_module.handle_equip_artifact(self.player, "пленка", self.vk, user_id=1)

        self.assertTrue(handled)
        equip_artifact.assert_called_once_with(1, "Плёнка")
        self.assertIn("Плёнка экипирован", self.vk.messages.sent[0]["message"])
        self.assertIn("Уклонение: +6%", self.vk.messages.sent[0]["message"])

    def test_handle_equip_artifact_number_uses_current_artifact_section(self):
        self.player.inventory_section = "artifacts"

        with patch.object(self.inventory_module, "_handle_artifact_digit", return_value=True) as handle_digit:
            handled = self.inventory_module.handle_equip_artifact(self.player, "1", self.vk, user_id=1)

        self.assertTrue(handled)
        handle_digit.assert_called_once_with(self.player, 0, self.vk, 1)

    def test_inventory_sections_edit_existing_inventory_screen(self):
        self.inventory_module.show_all(self.player, self.vk, user_id=9901)
        self.inventory_module.show_weapons(self.player, self.vk, user_id=9901)

        self.assertEqual(len(self.vk.messages.sent), 1)
        self.assertEqual(len(self.vk.messages.edited), 1)
        self.assertEqual(self.vk.messages.edited[0]["peer_id"], 9901)
        self.assertEqual(self.vk.messages.edited[0]["message_id"], 1)
        self.assertIn("ИНВЕНТАРЬ: ОРУЖИЕ", self.vk.messages.edited[0]["message"])

    def test_inventory_section_buttons_are_callbacks(self):
        keyboard = json.loads(create_inventory_keyboard().get_keyboard())
        first_button = keyboard["buttons"][0][0]
        payload = json.loads(first_button["action"]["payload"])

        self.assertEqual(first_button["action"]["type"], "callback")
        self.assertEqual(payload, {"command": "inventory_section", "section": "weapons"})

    def test_inventory_keyboard_stays_lower_ui_even_if_inline_requested(self):
        keyboard = json.loads(create_inventory_keyboard(inline=True).get_keyboard())

        self.assertFalse(keyboard["inline"])
        self.assertIn("Назад", json.dumps(keyboard, ensure_ascii=False))

    def test_inventory_back_button_uses_inventory_back_callback(self):
        keyboard = json.loads(create_inventory_keyboard().get_keyboard())
        back_button = keyboard["buttons"][-1][0]
        payload = json.loads(back_button["action"]["payload"])

        self.assertEqual(back_button["action"]["type"], "callback")
        self.assertEqual(payload, {"command": "inventory_back"})

    def test_inventory_hud_keyboard_has_only_page_callbacks(self):
        keyboard = json.loads(create_inventory_hud_keyboard(section="weapons", page=0, total_pages=3).get_keyboard())
        page_buttons = keyboard["buttons"][0]

        self.assertTrue(keyboard["inline"])
        self.assertEqual(json.loads(page_buttons[0]["action"]["payload"]), {"command": "inventory_page", "section": "weapons", "page": 2})
        self.assertEqual(json.loads(page_buttons[1]["action"]["payload"]), {"command": "inventory_page", "section": "weapons", "page": 0})
        self.assertEqual(json.loads(page_buttons[2]["action"]["payload"]), {"command": "inventory_page", "section": "weapons", "page": 1})
        self.assertEqual(len(keyboard["buttons"]), 1)

    def test_inventory_summary_uses_lower_category_keyboard_without_pages(self):
        invalidate_edit_targets(8802)

        self.inventory_module.show_all(self.player, self.vk, user_id=8802)
        message = self.vk.messages.sent[0]["message"]
        keyboard = json.loads(self.vk.messages.sent[0]["keyboard"])

        self.assertNotIn("Страница:", message)
        self.assertFalse(keyboard["inline"])
        self.assertEqual(
            json.loads(keyboard["buttons"][0][0]["action"]["payload"]),
            {"command": "inventory_section", "section": "weapons"},
        )

    def test_inventory_section_outputs_ten_items_per_page(self):
        invalidate_edit_targets(8801)
        self.player.inventory.weapons = [
            {"name": f"ПМ-{idx:02d}", "quantity": 1, "attack": idx, "weight": 1.0}
            for idx in range(1, 13)
        ]

        self.inventory_module.show_weapons(self.player, self.vk, user_id=8801, page=0)
        first_page = self.vk.messages.sent[0]["message"]
        self.inventory_module.show_weapons(self.player, self.vk, user_id=8801, page=1)
        second_page = self.vk.messages.edited[-1]["message"]

        self.assertIn("Страница: 1/2", first_page)
        self.assertIn("1. 🔫 ПМ-01", first_page)
        self.assertIn("10. 🔫 ПМ-10", first_page)
        self.assertNotIn("11. 🔫 ПМ-11", first_page)
        self.assertIn("Страница: 2/2", second_page)
        self.assertIn("11. 🔫 ПМ-11", second_page)
        self.assertIn("12. 🔫 ПМ-12", second_page)
        self.assertNotIn("10. 🔫 ПМ-10", second_page)

    def test_shop_hud_keyboard_has_page_callbacks(self):
        keyboard = json.loads(create_shop_hud_keyboard(view="sell", page=0, total_pages=3).get_keyboard())
        page_buttons = keyboard["buttons"][0]

        self.assertTrue(keyboard["inline"])
        self.assertEqual(json.loads(page_buttons[0]["action"]["payload"]), {"command": "shop_page", "view": "sell", "page": 2})
        self.assertEqual(json.loads(page_buttons[1]["action"]["payload"]), {"command": "shop_page", "view": "sell", "page": 0})
        self.assertEqual(json.loads(page_buttons[2]["action"]["payload"]), {"command": "shop_page", "view": "sell", "page": 1})
        self.assertEqual(
            json.loads(keyboard["buttons"][1][0]["action"]["payload"]),
            {"command": "sell_all_trash"},
        )

    def test_trader_shop_outputs_ten_items_per_page(self):
        invalidate_edit_targets(8811)
        self.inventory_module.clear_shop_cache(8811)
        self.inventory_module.database.NPC_MERCHANT_TRADER = "trader"
        self.inventory_module.database.get_npc_shop_assortment = Mock(return_value={
            "items": [
                {
                    "name": f"Товар-{idx:02d}",
                    "quantity": 1,
                    "category": "meds",
                    "price": idx,
                    "base_price": idx,
                    "weight": 0.1,
                    "stock_left": 5,
                }
                for idx in range(1, 13)
            ],
            "period_key": "test",
            "event_text": "",
        })

        self.inventory_module.show_trader_shop_all(self.player, self.vk, user_id=8811, page=0)
        first_page = self.vk.messages.sent[0]["message"]
        self.inventory_module.show_trader_shop_all(self.player, self.vk, user_id=8811, page=1)
        second_page = self.vk.messages.edited[-1]["message"]

        self.assertIn("Страница: 1/2", first_page)
        self.assertIn("1. 💊 Товар-01", first_page)
        self.assertIn("10. 💊 Товар-10", first_page)
        self.assertNotIn("11. 💊 Товар-11", first_page)
        self.assertIn("Страница: 2/2", second_page)
        self.assertIn("11. 💊 Товар-11", second_page)
        self.assertIn("12. 💊 Товар-12", second_page)
        self.assertNotIn("10. 💊 Товар-10", second_page)

    def test_buy_by_number_resolves_trader_all_cache(self):
        self.inventory_module.clear_shop_cache(777)
        self.inventory_module.set_shop_cache_data(777, {
            "merchant": "trader",
            "trader_all": [{"name": "Бинт"}, {"name": "Аптечка"}],
        })

        item_name, key = self.inventory_module._get_shop_item_by_number_any(
            777,
            2,
            ("trader_all", "weapons"),
        )

        self.assertEqual(item_name, "Аптечка")
        self.assertEqual(key, "trader_all")

    def test_handle_buy_item_accepts_trader_all_and_partial_unique_name(self):
        class Buyer(DummyPlayer):
            def __init__(self):
                super().__init__()
                self.bought = []

            def buy_item(self, item_name, merchant_id=None):
                self.bought.append((item_name, merchant_id))
                return True, f"Куплено {item_name}"

        player = Buyer()
        self.inventory_module.clear_shop_cache(778)
        self.inventory_module.set_shop_cache_data(778, {
            "merchant": "trader",
            "trader_all": [{"name": "Аптечка"}, {"name": "Бинт"}],
        })

        with patch.object(self.inventory_module, "show_trader_shop_all"):
            self.inventory_module.handle_buy_item(player, "апт", self.vk, 778)

        self.assertEqual(player.bought, [("Аптечка", "trader")])
        self.assertIn("Витрина Барыги обновлена", self.vk.messages.sent[0]["message"])

    def test_trader_sell_list_hides_equipped_and_event_items(self):
        self.player.inventory.weapons = [
            {"name": "ПМ", "quantity": 1, "attack": 10, "weight": 1.0},
            {"name": "АК-74 «Резонанс»", "quantity": 1, "attack": 145, "weight": 3.2},
            {"name": "ТТ", "quantity": 1, "attack": 20, "weight": 1.0},
        ]
        self.player.inventory.armor = [{"name": "Куртка", "quantity": 1, "defense": 5, "weight": 2.0}]
        self.player.inventory.artifacts = [{"name": "Медуза", "quantity": 1, "weight": 0.5}]
        self.inventory_module.database.NPC_MERCHANT_TRADER = "trader"
        self.inventory_module.database.get_shop_event_text = Mock(return_value="")
        self.inventory_module.database.get_npc_sell_price_preview = Mock(return_value={"sell_price": 10})

        self.inventory_module.show_trader_sell_all(self.player, self.vk, 779)
        message = self.vk.messages.sent[0]["message"]

        self.assertNotIn("ПМ", message)
        self.assertNotIn("Куртка", message)
        self.assertNotIn("АК-74 «Резонанс»", message)
        self.assertIn("ТТ", message)
        self.assertIn("Медуза", message)

    def test_sell_filter_allows_duplicate_when_one_copy_equipped(self):
        self.player.equipped_artifacts = ["Кристалл", "Кристальная колючка", "Бусы"]

        self.assertTrue(self.inventory_module._is_sellable_shop_item(
            self.player,
            {"name": "Кристалл", "quantity": 2, "weight": 0.5},
        ))
        self.assertTrue(self.inventory_module._is_sellable_shop_item(
            self.player,
            {"name": "Кристальная колючка", "quantity": 2, "weight": 0.5},
        ))
        self.assertFalse(self.inventory_module._is_sellable_shop_item(
            self.player,
            {"name": "Бусы", "quantity": 1, "weight": 0.5},
        ))

    def test_sell_artifacts_shows_inventory_duplicate_of_equipped_artifact(self):
        self.player.equipped_artifacts = ["Кристалл", "Кристальная колючка", "Бусы"]
        self.player.inventory.artifacts = [
            {"name": "Кристалл", "quantity": 2, "weight": 0.5},
            {"name": "Кристальная колючка", "quantity": 2, "weight": 0.5},
            {"name": "Бусы", "quantity": 1, "weight": 0.5},
        ]
        self.inventory_module.database.NPC_MERCHANT_TRADER = "trader"
        self.inventory_module.database.get_shop_event_text = Mock(return_value="")
        self.inventory_module.database.get_npc_sell_price_preview = Mock(return_value={"sell_price": 10})

        self.inventory_module.show_sell_artifacts(self.player, self.vk, 780)
        message = self.vk.messages.sent[0]["message"]

        self.assertIn("Кристалл", message)
        self.assertIn("Кристальная колючка", message)
        self.assertNotIn("Бусы", message)


if __name__ == "__main__":
    unittest.main()
