import unittest

from game.location_mechanics import LOCATION_MODIFIERS, get_event_weights
from game.map_schema import get_map_location
from handlers.combat import RESEARCH_EVENTS, _is_research_event_allowed_for_location


class InternalZoneUniqueContentTests(unittest.TestCase):
    def test_internal_zones_have_own_event_pools(self):
        old_road_events = {"military_cache", "field_lab_data", "blood_trail", "abandoned_camp"}
        for location_id in ("военная_часть", "главный_корпус_нии", "зараженный_лес"):
            pool = set(LOCATION_MODIFIERS[location_id].get("event_pool", []))
            self.assertGreaterEqual(len(pool), 6, location_id)
            self.assertTrue(pool.isdisjoint(old_road_events), location_id)

            for event_id in pool:
                self.assertIn(event_id, RESEARCH_EVENTS, f"{location_id}: missing event {event_id}")
                locations = set(RESEARCH_EVENTS[event_id].get("locations") or [])
                if locations:
                    self.assertIn(location_id, locations, f"{event_id} not tagged for {location_id}")

    def test_unique_events_are_blocked_outside_their_marked_location(self):
        cases = [
            ("armory_locker", "военная_часть", "дорога_военная_часть"),
            ("sealed_archive", "главный_корпус_нии", "дорога_нии"),
            ("bone_cache", "зараженный_лес", "дорога_зараженный_лес"),
        ]

        for event_id, allowed_location, blocked_location in cases:
            event = RESEARCH_EVENTS[event_id]
            self.assertTrue(
                _is_research_event_allowed_for_location(event_id, event, allowed_location, get_event_weights(allowed_location))
            )
            self.assertFalse(
                _is_research_event_allowed_for_location(event_id, event, blocked_location, get_event_weights(blocked_location))
            )

    def test_internal_event_pools_filter_selection_candidates(self):
        military_weights = get_event_weights("военная_часть")
        self.assertTrue(
            _is_research_event_allowed_for_location(
                "armory_locker",
                RESEARCH_EVENTS["armory_locker"],
                "военная_часть",
                military_weights,
            )
        )
        self.assertFalse(
            _is_research_event_allowed_for_location(
                "military_cache",
                RESEARCH_EVENTS["military_cache"],
                "военная_часть",
                military_weights,
            )
        )

    def test_internal_zones_have_distinct_loot_profiles(self):
        self.assertEqual(LOCATION_MODIFIERS["военная_часть"]["loot_quality"], "military")
        self.assertEqual(LOCATION_MODIFIERS["главный_корпус_нии"]["loot_quality"], "scientific")
        self.assertEqual(LOCATION_MODIFIERS["зараженный_лес"]["loot_quality"], "organic")

        self.assertEqual(get_map_location("дорога_военная_часть")["loot_profile"], "military")
        self.assertEqual(get_map_location("военная_часть")["loot_profile"], "military_base")
        self.assertEqual(get_map_location("дорога_нии")["loot_profile"], "scientific")
        self.assertEqual(get_map_location("главный_корпус_нии")["loot_profile"], "nii_core")
        self.assertEqual(get_map_location("дорога_зараженный_лес")["loot_profile"], "organic")
        self.assertEqual(get_map_location("зараженный_лес")["loot_profile"], "deep_forest")

        self.assertIn("armory_locker", LOCATION_MODIFIERS["военная_часть"]["event_pool"])
        self.assertIn("sealed_archive", LOCATION_MODIFIERS["главный_корпус_нии"]["event_pool"])
        self.assertIn("bone_cache", LOCATION_MODIFIERS["зараженный_лес"]["event_pool"])


if __name__ == "__main__":
    unittest.main()
