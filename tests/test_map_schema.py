import unittest

from game.constants import RESEARCH_LOCATIONS, SAFE_LOCATIONS
from game.map_schema import (
    DANGER_LEVELS,
    LOCATION_TYPES,
    MAP_LOCATIONS,
    assert_valid_map_schema,
    get_map_location,
    get_map_locations,
    get_locations_by_region,
    get_locations_by_type,
    get_research_map_locations,
    validate_location_requires,
    validate_map_schema,
)
from models.locations import LOCATIONS


class MapSchemaTests(unittest.TestCase):
    def test_structured_map_keeps_legacy_locations_compatible(self):
        self.assertEqual(set(MAP_LOCATIONS.keys()), set(LOCATIONS.keys()))

        for location_id, legacy in LOCATIONS.items():
            record = get_map_location(location_id)
            self.assertIsNotNone(record)
            self.assertEqual(record["id"], location_id)
            self.assertEqual(record["name"], legacy["name"])
            self.assertEqual(record["exits"], legacy["exits"])
            self.assertEqual(record["legacy_actions"], legacy["actions"])

    def test_every_map_record_has_required_architecture_fields(self):
        required_fields = {
            "id",
            "name",
            "region",
            "type",
            "level_min",
            "level_max",
            "danger",
            "tags",
            "requires",
            "exits",
            "activities",
            "loot_profile",
        }

        for location_id, record in get_map_locations().items():
            self.assertTrue(required_fields.issubset(record.keys()), location_id)
            self.assertIn(record["type"], LOCATION_TYPES)
            self.assertIn(record["danger"], DANGER_LEVELS)
            self.assertLessEqual(record["level_min"], record["level_max"])
            self.assertIsInstance(record["tags"], list)
            self.assertIsInstance(record["requires"], dict)
            self.assertIsInstance(record["activities"], list)

    def test_map_schema_validator_passes_current_baseline(self):
        self.assertEqual(validate_map_schema(), [])
        assert_valid_map_schema()

    def test_research_locations_are_typed_as_routes_with_research_activity(self):
        for location_id in RESEARCH_LOCATIONS:
            record = get_map_location(location_id)
            self.assertEqual(record["type"], "route")
            self.assertIn("research", record["activities"])
            self.assertIn("research", record["tags"])
            self.assertIsNotNone(record["loot_profile"])

        self.assertEqual(
            [record["id"] for record in get_research_map_locations()],
            list(RESEARCH_LOCATIONS),
        )

    def test_safe_locations_are_safe_hubs_or_safehouses(self):
        for location_id in SAFE_LOCATIONS:
            record = get_map_location(location_id)
            self.assertEqual(record["danger"], "safe")
            self.assertIn(record["type"], {"hub", "safehouse"})

    def test_region_and_type_helpers_return_structured_records(self):
        city_locations = {record["id"] for record in get_locations_by_region("city")}
        self.assertIn("город", city_locations)
        self.assertIn("убежище", city_locations)

        route_locations = {record["id"] for record in get_locations_by_type("route")}
        self.assertEqual(route_locations, set(RESEARCH_LOCATIONS))

    def test_requirement_validator_accepts_future_access_shapes(self):
        errors = validate_location_requires(
            "test_location",
            {
                "level": 10,
                "rank_tier": 3,
                "key": "old_bunker_key",
                "items": ["Антирад", "Дозиметр"],
                "flags": ["opened_nii_basement"],
                "reputation": {"ученые": 25},
                "radiation_max": 80,
                "money": 500,
            },
        )
        self.assertEqual(errors, [])

    def test_requirement_validator_rejects_unknown_or_bad_requirements(self):
        errors = validate_location_requires(
            "bad_location",
            {
                "unknown": True,
                "level": "10",
                "items": ["Антирад", ""],
                "reputation": {"": "high"},
            },
        )
        self.assertGreaterEqual(len(errors), 4)


if __name__ == "__main__":
    unittest.main()
