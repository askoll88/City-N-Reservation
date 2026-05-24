import random
import time
import unittest
from unittest.mock import patch

from game.fishing import (
    FISHING_DURATION_SECONDS,
    FISH_LOCKER_CAPACITY,
    FISH_SPECIES,
    LAKE_LOCATION,
    SPOTS,
    _roll_fish_entry,
    _select_gear,
    check_fishing,
    complete_luchik_order,
    cook_recipe,
    buy_luchik_shop_item,
    sell_luchik_fish,
    show_fish_locker,
    start_fishing,
)
from game.map_schema import get_map_location


class DummyMessages:
    def __init__(self):
        self.sent = []

    def send(self, **kwargs):
        self.sent.append(kwargs)
        return 1


class DummyVk:
    def __init__(self):
        self.messages = DummyMessages()


class DummyPlayer:
    user_id = 777
    current_location_id = LAKE_LOCATION
    level = 28
    energy = 50
    max_energy = 100
    health = 100
    max_health = 100
    radiation = 0
    perception = 5
    luck = 5

    def add_experience(self, amount):
        return amount

    def buy_item(self, item_name):
        self.money -= 10
        return True, f"Ты купил {item_name}"


class FishingSystemTest(unittest.TestCase):
    def test_lake_is_midgame_fishing_location(self):
        tourbase = get_map_location("турбаза_лучик")
        lake = get_map_location("озеро")

        self.assertEqual(tourbase["type"], "safehouse")
        self.assertEqual(tourbase["level_min"], 24)
        self.assertEqual(lake["type"], "resource_job")
        self.assertEqual(lake["loot_profile"], "lake_fishing")

    def test_start_fishing_spends_energy_and_stores_state(self):
        player = DummyPlayer()
        vk = DummyVk()
        spot = SPOTS["deep"]

        with patch("game.fishing.service.database.get_runtime_state", return_value=None), \
             patch("game.fishing.service.database.get_inventory_item_quantities", return_value={}), \
             patch("game.fishing.service.database.set_runtime_state") as set_state, \
             patch("game.fishing.service.database.remove_item_from_inventory") as remove_item, \
             patch("game.fishing.service.database.update_user_stats") as update_stats:
            handled = start_fishing(player, vk, 777, "deep")

        self.assertTrue(handled)
        self.assertEqual(player.energy, 50 - spot.energy_cost)
        update_stats.assert_called_once_with(777, energy=player.energy)
        self.assertEqual(set_state.call_args.args[2]["spot"], "deep")
        self.assertEqual(set_state.call_args.args[2]["gear_label"], "Леска с крючком")
        remove_item.assert_not_called()
        self.assertIn("Глубокий заброс", vk.messages.sent[-1]["message"])

    def test_start_fishing_uses_best_gear_and_consumes_bait(self):
        player = DummyPlayer()
        vk = DummyVk()

        with patch("game.fishing.service.database.get_runtime_state", return_value=None), \
             patch("game.fishing.service.database.get_inventory_item_quantities", side_effect=[
                 {"Старая удочка": 1},
                 {"Черви": 3},
             ]), \
             patch("game.fishing.service.database.set_runtime_state") as set_state, \
             patch("game.fishing.service.database.remove_item_from_inventory") as remove_item, \
             patch("game.fishing.service.database.update_user_stats"):
            handled = start_fishing(player, vk, 777, "shore")

        self.assertTrue(handled)
        state = set_state.call_args.args[2]
        self.assertEqual(state["gear"], "Старая удочка")
        self.assertEqual(state["bait"], "Черви")
        remove_item.assert_called_once_with(777, "Черви", 1)
        self.assertIn("Старая удочка", vk.messages.sent[-1]["message"])

    def test_start_fishing_drops_bait_bonus_when_consume_fails(self):
        player = DummyPlayer()
        vk = DummyVk()

        with patch("game.fishing.service.database.get_runtime_state", return_value=None), \
             patch("game.fishing.service.database.get_inventory_item_quantities", side_effect=[
                 {},
                 {"Черви": 1},
             ]), \
             patch("game.fishing.service.database.set_runtime_state") as set_state, \
             patch("game.fishing.service.database.remove_item_from_inventory", return_value=False), \
             patch("game.fishing.service.database.update_user_stats"):
            handled = start_fishing(player, vk, 777, "shore")

        self.assertTrue(handled)
        state = set_state.call_args.args[2]
        self.assertEqual(state["bait"], "")
        self.assertIn("без наживки", vk.messages.sent[-1]["message"])

    def test_select_gear_falls_back_without_rod(self):
        with patch("game.fishing.service.database.get_inventory_item_quantities", return_value={}):
            gear = _select_gear(777)

        self.assertEqual(gear.label, "Леска с крючком")

    def test_check_fishing_grants_catch_after_timer(self):
        player = DummyPlayer()
        vk = DummyVk()
        state = {
            "started_at": int(time.time()) - FISHING_DURATION_SECONDS - 1,
            "duration": FISHING_DURATION_SECONDS,
            "spot": "shore",
            "gear": "Старая удочка",
            "bait": "Черви",
            "seed": 12345,
        }

        with patch("game.fishing.service.database.get_runtime_state", return_value=state), \
             patch("game.fishing.service.database.add_item_to_inventory", return_value=True) as add_item, \
             patch("game.fishing.service.database.add_fish_to_locker_transaction", return_value={"success": True}) as add_fish, \
             patch("game.fishing.service.database.clear_runtime_state") as clear_state, \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = check_fishing(player, vk, 777)

        self.assertTrue(handled)
        self.assertFalse(add_item.called)
        self.assertTrue(add_fish.called)
        clear_state.assert_called_once_with(777, "fishing_state")
        self.assertIn("Рыбалка завершена", vk.messages.sent[-1]["message"])

    def test_fish_entry_has_weight_and_value_in_range(self):
        fish = next(row for row in FISH_SPECIES if row.name == "Тяжелый карп")
        entry = _roll_fish_entry(fish, SPOTS["deep"], random.Random(7))

        self.assertGreaterEqual(entry["weight_kg"], fish.weight_min)
        self.assertLessEqual(entry["weight_kg"], fish.weight_max)
        self.assertGreaterEqual(entry["price_per_kg"], fish.price_per_kg_min)
        self.assertLessEqual(entry["price_per_kg"], fish.price_per_kg_max)
        self.assertEqual(entry["value"], int(round(entry["weight_kg"] * entry["price_per_kg"])))

    def test_fish_pool_is_large_unique_and_weighted(self):
        names = [fish.name for fish in FISH_SPECIES]

        self.assertGreaterEqual(len(FISH_SPECIES), 200)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue({"common", "uncommon", "rare"}.issubset({fish.tier for fish in FISH_SPECIES}))
        for fish in FISH_SPECIES:
            self.assertLess(fish.weight_min, fish.weight_max, fish.name)
            self.assertLess(fish.price_per_kg_min, fish.price_per_kg_max, fish.name)
            self.assertTrue(fish.spots, fish.name)

        self.assertNotIn("Малая окунь", names)
        self.assertIn("Малый окунь", names)
        self.assertNotIn("Аномальная карась", names)
        self.assertIn("Аномальный карась", names)

    def test_luchik_sells_weighted_fish_locker(self):
        player = DummyPlayer()
        player.money = 100
        vk = DummyVk()
        locker_sale = {
            "success": True,
            "sold": [{"name": "Тяжелый карп", "weight_kg": 3.25, "value": 520}],
            "total": 520,
            "remaining_money": 620,
        }

        with patch("game.fishing.service.database.sell_fish_locker_transaction", return_value=locker_sale) as sell_locker, \
             patch("game.fishing.service.database.sell_luchik_fish_transaction", return_value={"success": False, "total": 0}), \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = sell_luchik_fish(player, vk, 777, "лучик")

        self.assertTrue(handled)
        sell_locker.assert_called_once_with(777)
        self.assertTrue(getattr(player, "_luchik_last_sale_success", False))
        self.assertEqual(player.money, 620)
        self.assertIn("3.25 кг", vk.messages.sent[-1]["message"])

    def test_luchik_does_not_track_sale_when_locker_is_empty(self):
        player = DummyPlayer()
        vk = DummyVk()

        with patch("game.fishing.service.database.sell_fish_locker_transaction", return_value={"success": False, "total": 0, "message": "В рыбном шкафу нет рыбы."}), \
             patch("game.fishing.service.database.sell_luchik_fish_transaction", return_value={"success": False, "total": 0, "message": "У тебя нет рыбы, которую берёт Лучик."}):
            handled = sell_luchik_fish(player, vk, 777, "лучик")

        self.assertTrue(handled)
        self.assertFalse(getattr(player, "_luchik_last_sale_success", False))
        self.assertIn("рыбы", vk.messages.sent[-1]["message"])

    def test_cooking_consumes_fish_from_tourbase_locker(self):
        player = DummyPlayer()
        player.current_location_id = "турбаза_лучик"
        vk = DummyVk()
        consumed = [
            {"name": "Серебристая плотва", "weight_kg": 0.4, "value": 28},
            {"name": "Пятнистый окунь", "weight_kg": 0.6, "value": 51},
        ]

        with patch("game.fishing.service.database.consume_fish_locker_entries_transaction", return_value={"success": True, "used_text": "Серебристая плотва x1, Пятнистый окунь x1", "consumed": consumed}) as consume, \
             patch("game.fishing.service.database.cook_luchik_recipe_transaction", return_value={"success": True, "message": "Готово: Уха у Лучика x1. Списано: Чистая вода x1"}), \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = cook_recipe(player, vk, 777, "уха")

        self.assertTrue(handled)
        consume.assert_called_once()
        self.assertIn("Из рыбного шкафа", vk.messages.sent[-1]["message"])

    def test_cooking_consumes_cheapest_matching_fish_from_locker(self):
        player = DummyPlayer()
        player.current_location_id = "турбаза_лучик"
        vk = DummyVk()
        consumed = [
            {"name": "Пятнистый окунь", "weight_kg": 0.6, "value": 40},
            {"name": "Старый карась", "weight_kg": 0.7, "value": 50},
        ]

        with patch("game.fishing.service.database.consume_fish_locker_entries_transaction", return_value={"success": True, "used_text": "Пятнистый окунь x1, Старый карась x1", "consumed": consumed}) as consume, \
             patch("game.fishing.service.database.cook_luchik_recipe_transaction", return_value={"success": True, "message": "Готово"}), \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = cook_recipe(player, vk, 777, "уха")

        self.assertTrue(handled)
        self.assertEqual(consume.call_args.args[2], 2)

    def test_luchik_order_consumes_fish_from_tourbase_locker(self):
        player = DummyPlayer()
        player.current_location_id = "турбаза_лучик"
        vk = DummyVk()
        consumed = [
            {"name": "Серебристая плотва", "weight_kg": 0.4, "value": 28},
            {"name": "Пятнистый окунь", "weight_kg": 0.6, "value": 51},
            {"name": "Старый карась", "weight_kg": 0.9, "value": 72},
        ]

        with patch("game.fishing.service.database.consume_fish_locker_entries_transaction", return_value={"success": True, "used_text": "Серебристая плотва x1, Пятнистый окунь x1, Старый карась x1", "consumed": consumed}), \
             patch("game.fishing.service.database.complete_luchik_order_transaction", return_value={"success": True, "message": "Заказ закрыт: Уха на вечер.\nСписано: ничего.\nНаграда: 340 руб.\nДенег сейчас: 500 руб."}), \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = complete_luchik_order(player, vk, 777, "common_fish")

        self.assertTrue(handled)
        self.assertIn("Списано из рыбного шкафа", vk.messages.sent[-1]["message"])

    def test_full_fish_locker_does_not_drop_existing_entries(self):
        player = DummyPlayer()
        vk = DummyVk()
        state = {
            "started_at": int(time.time()) - FISHING_DURATION_SECONDS - 1,
            "duration": FISHING_DURATION_SECONDS,
            "spot": "shore",
            "gear": "Старая удочка",
            "bait": "",
            "seed": 12345,
        }
        with patch("game.fishing.service.database.get_runtime_state", return_value=state), \
             patch("game.fishing.service.database.add_item_to_inventory", return_value=True), \
             patch("game.fishing.service.database.add_fish_to_locker_transaction", return_value={"success": False, "full": True}), \
             patch("game.fishing.service.database.clear_runtime_state"), \
             patch("game.fishing.service.invalidate_player_cache"):
            handled = check_fishing(player, vk, 777)

        self.assertTrue(handled)
        self.assertIn("шкаф турбазы заполнен", vk.messages.sent[-1]["message"])

    def test_show_fish_locker_lists_value_and_capacity(self):
        player = DummyPlayer()
        vk = DummyVk()
        entries = [{"name": "Тяжелый карп", "weight_kg": 3.25, "value": 520}]

        with patch("game.fishing.service.database.get_user_fish_locker", return_value=entries):
            handled = show_fish_locker(player, vk, 777)

        self.assertTrue(handled)
        message = vk.messages.sent[-1]["message"]
        self.assertIn(f"1/{FISH_LOCKER_CAPACITY}", message)
        self.assertIn("520 руб", message)

    def test_luchik_shop_buy_allows_fishing_items(self):
        player = DummyPlayer()
        player.current_location_id = "турбаза_лучик"
        player.money = 100
        vk = DummyVk()

        with patch("game.fishing.service.invalidate_player_cache"):
            handled = buy_luchik_shop_item(player, vk, 777, "2 черви")

        self.assertTrue(handled)
        self.assertEqual(player.money, 80)
        self.assertIn("Черви x2", vk.messages.sent[-1]["message"])


if __name__ == "__main__":
    unittest.main()
