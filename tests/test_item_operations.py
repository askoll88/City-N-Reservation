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


if __name__ == "__main__":
    unittest.main()
