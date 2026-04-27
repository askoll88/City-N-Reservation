import unittest

from game.constants import (
    ITEM_CATEGORY_DROP_CHANCES_BY_LOCATION,
    LOCATION_DROP_BALANCE_RULES,
    LOCATION_LEVEL_THRESHOLDS,
    RESEARCH_LOCATIONS,
    SAFE_LOCATIONS,
)
from game.location_mechanics import LOCATION_LOOT_BIAS, LOCATION_MODIFIERS
from handlers.combat import RESEARCH_EVENTS
from models.enemies import ENEMIES
from models.locations import LOCATIONS


class MapBaselineTests(unittest.TestCase):
    def test_core_locations_and_exits_are_present(self):
        required = {
            "город",
            "кпп",
            "больница",
            "черный рынок",
            "убежище",
            "инвентарь",
            "дорога_военная_часть",
            "дорога_нии",
            "дорога_зараженный_лес",
        }
        self.assertTrue(required.issubset(LOCATIONS.keys()))

        city_exits = LOCATIONS["город"]["exits"]
        self.assertEqual(city_exits["кпп"], "кпп")
        self.assertEqual(city_exits["больница"], "больница")
        self.assertEqual(city_exits["черный рынок"], "черный рынок")
        self.assertEqual(city_exits["убежище"], "убежище")

        kpp_exits = LOCATIONS["кпп"]["exits"]
        self.assertEqual(kpp_exits["город"], "город")
        self.assertEqual(kpp_exits["дорога на военную часть"], "дорога_военная_часть")
        self.assertEqual(kpp_exits["дорога на нии"], "дорога_нии")
        self.assertEqual(kpp_exits["дорога на зараженный лес"], "дорога_зараженный_лес")

    def test_all_location_exits_point_to_existing_locations(self):
        for location_id, location in LOCATIONS.items():
            self.assertIn("name", location)
            self.assertIn("description", location)
            self.assertIn("exits", location)
            for alias, target_id in location["exits"].items():
                self.assertIn(
                    target_id,
                    LOCATIONS,
                    f"{location_id}: exit '{alias}' points to missing location '{target_id}'",
                )

    def test_safe_locations_are_known_locations(self):
        for location_id in SAFE_LOCATIONS:
            self.assertIn(location_id, LOCATIONS)

    def test_research_locations_have_complete_runtime_data(self):
        for location_id in RESEARCH_LOCATIONS:
            self.assertIn(location_id, LOCATIONS)
            self.assertIn(location_id, LOCATION_MODIFIERS)
            self.assertIn(location_id, ENEMIES)
            self.assertIn(location_id, ITEM_CATEGORY_DROP_CHANCES_BY_LOCATION)
            self.assertIn(location_id, LOCATION_LEVEL_THRESHOLDS)
            self.assertIn(location_id, LOCATION_DROP_BALANCE_RULES)

    def test_enemy_tables_are_rollable(self):
        for location_id in RESEARCH_LOCATIONS:
            enemies = ENEMIES[location_id]
            self.assertGreater(len(enemies), 0)
            self.assertGreater(sum(int(enemy.get("chance", 0) or 0) for enemy in enemies), 0)
            for enemy in enemies:
                self.assertGreater(int(enemy.get("hp", 0) or 0), 0)
                self.assertGreater(int(enemy.get("damage", 0) or 0), 0)
                self.assertGreater(int(enemy.get("chance", 0) or 0), 0)

    def test_location_event_weights_reference_known_research_events(self):
        known_event_types = {
            "enemy",
            "item",
            "artifact",
            "artifact_cluster",
            "anomaly",
            "radiation",
            "trap",
            "stash",
            "survivor",
            "shell_cache",
            "intel",
            "camp",
            "psi",
            "trail",
        }
        for location_id, modifier in LOCATION_MODIFIERS.items():
            for event_id in modifier.get("event_weights", {}):
                if event_id in RESEARCH_EVENTS:
                    continue
                self.assertIn(event_id, known_event_types, f"{location_id}: unknown event weight {event_id}")

    def test_loot_bias_is_attached_to_known_research_locations(self):
        for location_id, bias in LOCATION_LOOT_BIAS.items():
            self.assertIn(location_id, RESEARCH_LOCATIONS)
            self.assertGreater(len(bias.get("bias_items", [])), 0)
            self.assertGreater(float(bias.get("bias_weight", 0) or 0), 0)


if __name__ == "__main__":
    unittest.main()
