import unittest
from unittest.mock import patch

from infra import config, database
from models.player import Inventory, Player


class ItemOperationsTest(unittest.TestCase):
    def test_user_dict_exposes_all_artifact_equipment_slots(self):
        user = {"id": 1, "vk_id": 1, "artifact_slots": config.MAX_ARTIFACT_SLOTS}
        equipment = [
            {"slot": "artifact_1", "item_name": "Медуза"},
            {"slot": f"artifact_{config.MAX_ARTIFACT_SLOTS}", "item_name": "Душа"},
        ]

        result = database._build_user_dict(user, equipment, [])

        self.assertEqual(result["equipped_artifact_1"], "Медуза")
        self.assertEqual(result[f"equipped_artifact_{config.MAX_ARTIFACT_SLOTS}"], "Душа")

    def test_player_equipped_artifacts_uses_all_configured_slots(self):
        player = Player.__new__(Player)
        for idx in range(1, config.MAX_ARTIFACT_SLOTS + 1):
            setattr(player, f"equipped_artifact_{idx}", None)
        player.equipped_artifact_1 = "Медуза"
        setattr(player, f"equipped_artifact_{config.MAX_ARTIFACT_SLOTS}", "Душа")

        self.assertEqual(player.equipped_artifacts, ["Медуза", "Душа"])

    def test_inventory_weight_counts_shells_bags(self):
        inventory = Inventory.__new__(Inventory)
        inventory.weapons = []
        inventory.armor = []
        inventory.backpacks = []
        inventory.artifacts = []
        inventory.shells_bags = [{"name": "Маленький мешочек", "quantity": 1, "weight": 0.2}]
        inventory.other = []

        self.assertEqual(inventory.total_weight, 0.2)

    @patch("infra.database.update_user_stats")
    @patch("infra.database.get_item_by_name", return_value={"name": "Маленький мешочек", "backpack_bonus": 10})
    @patch("infra.database.get_user_by_vk")
    def test_get_shells_info_clamps_overfilled_equipped_bag(self, get_user_mock, _item_mock, update_stats_mock):
        get_user_mock.return_value = {
            "shells": 35,
            "equipped_shells_bag": "Маленький мешочек",
        }

        info = database.get_shells_info(1)

        self.assertEqual(info["current"], 10)
        self.assertEqual(info["capacity"], 10)
        update_stats_mock.assert_called_once_with(1, shells=10)

    @patch("infra.database.db_cursor")
    def test_add_item_rejects_non_positive_quantity_before_db(self, db_cursor_mock):
        self.assertFalse(database.add_item_to_inventory(1, "Бинт", 0))
        self.assertFalse(database.add_item_to_inventory(1, "Бинт", -3))
        db_cursor_mock.assert_not_called()

    @patch("infra.database.db_cursor")
    def test_remove_item_rejects_non_positive_quantity_before_db(self, db_cursor_mock):
        self.assertFalse(database.remove_item_from_inventory(1, "Бинт", 0))
        self.assertFalse(database.remove_item_from_inventory(1, "Бинт", -3))
        db_cursor_mock.assert_not_called()

    @patch("infra.database.db_cursor")
    def test_drop_item_rejects_non_positive_quantity_before_db(self, db_cursor_mock):
        result = database.drop_item_from_inventory(1, "Бинт", 0)

        self.assertFalse(result["success"])
        db_cursor_mock.assert_not_called()

    def test_storage_slot_usage_counts_item_rows_not_stack_quantity(self):
        rows = [
            {"item_id": 1, "quantity": 100},
            {"item_id": 2, "quantity": 26},
        ]

        slots, has_existing = database._storage_slot_usage(rows, 1)
        slots_for_new, has_new = database._storage_slot_usage(rows, 3)

        self.assertEqual(slots, 2)
        self.assertTrue(has_existing)
        self.assertEqual(slots_for_new, 2)
        self.assertFalse(has_new)

    @patch("infra.database.update_user_stats")
    @patch("infra.database.get_user_inventory")
    @patch("infra.database.get_user_by_vk")
    def test_equip_artifact_uses_purchased_slots_above_three(
        self,
        get_user_mock,
        get_inventory_mock,
        update_stats_mock,
    ):
        get_user_mock.return_value = {
            "artifact_slots": 4,
            "equipped_artifact_1": "Медуза",
            "equipped_artifact_2": "Пустышка",
            "equipped_artifact_3": "Капля",
            "equipped_artifact_4": None,
        }
        get_inventory_mock.return_value = [{"name": "Душа", "category": "artifacts"}]

        result = database.equip_artifact(1, "Душа")

        self.assertTrue(result["success"])
        update_stats_mock.assert_called_once_with(1, equipped_artifact_4="Душа")

    def test_artifact_energy_bonus_increases_player_max_energy(self):
        player = Player.__new__(Player)
        player._artifact_bonuses = {"energy": 15, "max_energy": 20}
        player.stamina = 4
        player._get_passive_bonuses = lambda: {}

        self.assertEqual(player.max_energy, 135)

    def test_artifact_damage_resist_reduces_incoming_damage_after_defense(self):
        player = Player.__new__(Player)
        player._artifact_bonuses = {"damage_resist": 25}
        player._get_passive_bonuses = lambda: {}

        self.assertEqual(player.damage_resist, 25)

    def test_event_outfit_passives_apply_without_class(self):
        player = Player.__new__(Player)
        player.player_class = None
        player.level = 1
        player.perception = 5
        player.luck = 5
        player.equipped_device = None
        player.equipped_armor = None
        player.equipped_armor_head = None
        player.equipped_armor_body = "Плащ «Проводник Сигнала»"
        player.equipped_armor_legs = None
        player.equipped_armor_hands = "Перчатки «Проводник Сигнала»"
        player.equipped_armor_feet = "Ботинки «Проводник Сигнала»"
        player._artifact_bonuses = {}

        passive = player._get_passive_bonuses()

        self.assertEqual(passive["find_chance"], 8)
        self.assertEqual(passive["rare_find_chance"], 4)
        self.assertEqual(passive["artifact_extract_bonus_pct"], 8)
        self.assertEqual(passive["precise_anomaly_shell_discount"], 1)
        self.assertEqual(passive["travel_time_reduction_pct"], 7)
        self.assertEqual(player.find_chance, 23)

    @patch("models.player.database.update_user_stats")
    @patch("models.player.database.get_artifact_bonuses", return_value={"energy": 20})
    @patch("models.player.database.get_user_by_vk")
    def test_player_reload_refreshes_artifact_slots_and_equipped_artifacts(
        self,
        get_user_mock,
        get_artifact_bonuses_mock,
        update_stats_mock,
    ):
        player = Player.__new__(Player)
        player.user_id = 1
        player.inventory = Inventory.__new__(Inventory)
        player.inventory.reload = lambda: None
        player._recalculate_max_weight = lambda: None
        player._get_passive_bonuses = lambda: {}
        player._data = {}

        data = {
            "location": "город",
            "health": 100,
            "energy": 130,
            "radiation": 0,
            "money": 0,
            "level": 1,
            "experience": 0,
            "strength": 4,
            "stamina": 4,
            "perception": 4,
            "luck": 4,
            "armor_defense": 0,
            "equipped_backpack": None,
            "equipped_weapon": None,
            "equipped_armor": None,
            "equipped_device": None,
            "newbie_kit_received": 0,
            "artifact_slots": 4,
            "inventory_section": None,
            "previous_location": None,
            "is_admin": 0,
            "is_banned": 0,
            "ban_reason": None,
            "equipped_armor_head": None,
            "equipped_armor_body": None,
            "equipped_armor_legs": None,
            "equipped_armor_hands": None,
            "equipped_armor_feet": None,
        }
        for idx in range(1, config.MAX_ARTIFACT_SLOTS + 1):
            data[f"equipped_artifact_{idx}"] = None
        data["equipped_artifact_4"] = "Лунный свет"
        get_user_mock.return_value = data

        player.reload()

        self.assertEqual(player.artifact_slots, 4)
        self.assertEqual(player.equipped_artifact_4, "Лунный свет")
        self.assertEqual(player.energy, 120)
        update_stats_mock.assert_called_with(1, energy=120)


if __name__ == "__main__":
    unittest.main()
