import unittest

from game.constants import RESEARCH_LOCATIONS
from game.random_events import QUEST_CHAINS, RANDOM_EVENTS, get_event_corridors, get_random_event


NEW_RANDOM_EVENT_IDS = {
    "silent_checkpoint_lamp",
    "black_box_whisper",
    "rusted_iconostasis",
    "fogged_bus_children",
    "dead_drop_locker",
    "glass_grass",
    "market_receipt_wind",
    "wire_angel",
    "rain_inside_room",
    "red_thread_map",
    "frozen_radio_tower",
    "mutant_bell_collar",
    "canteen_last_menu",
    "white_noise_prayer",
    "ash_snowman",
    "hospital_pager",
    "negative_shadow",
    "ledger_of_debts",
    "tin_can_oracle",
    "sleeping_detector",
    "red_water_puddle",
    "mechanical_bees",
    "telephone_to_kpp",
    "chalk_circle_trade",
    "elevator_in_field",
    "singing_powerline",
    "mirror_well",
    "paper_cranes",
}


NEW_CHAIN_KEYS = {"black_beacon", "rain_archive"}


class RandomEventsContentTests(unittest.TestCase):
    def test_event_ids_are_unique(self):
        ids = [event["id"] for event in RANDOM_EVENTS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_events_are_bound_to_known_corridors(self):
        known_corridors = set(RESEARCH_LOCATIONS)
        for event in RANDOM_EVENTS:
            corridors = get_event_corridors(event["id"])
            self.assertGreater(len(corridors), 0, event["id"])
            self.assertTrue(set(corridors).issubset(known_corridors), event["id"])

    def test_new_random_events_are_present_and_actionable(self):
        events_by_id = {event["id"]: event for event in RANDOM_EVENTS}
        self.assertTrue(NEW_RANDOM_EVENT_IDS.issubset(events_by_id))

        for event_id in NEW_RANDOM_EVENT_IDS:
            event = events_by_id[event_id]
            self.assertGreater(int(event.get("chance_weight", 0)), 0)
            self.assertIn("type", event)
            self.assertGreaterEqual(len(event.get("choices", [])), 2)
            for choice in event["choices"]:
                self.assertIn("label", choice)
                self.assertIn("effect", choice)

    def test_new_long_quest_chains_reference_existing_events(self):
        events_by_id = {event["id"]: event for event in RANDOM_EVENTS}

        for chain_key in NEW_CHAIN_KEYS:
            self.assertIn(chain_key, QUEST_CHAINS)
            chain = QUEST_CHAINS[chain_key]
            self.assertGreaterEqual(len(chain["stages"]), 5)
            for stage_events in chain["stages"]:
                self.assertEqual(len(stage_events), 1)
                self.assertIn(stage_events[0], events_by_id)

    def test_random_event_selection_respects_corridor_filter(self):
        seen = set()
        for _ in range(3000):
            event = get_random_event(corridor_id="военная_часть", guaranteed=True)
            if event:
                seen.add(event["id"])

        self.assertIn("military_patrol", seen)
        self.assertNotIn("rain_archive_reading_room", seen)

    def test_guaranteed_random_event_returns_corridor_event(self):
        for corridor_id in RESEARCH_LOCATIONS:
            event = get_random_event(corridor_id=corridor_id, guaranteed=True)

            self.assertIsNotNone(event, corridor_id)
            self.assertIn(corridor_id, get_event_corridors(event["id"]))


if __name__ == "__main__":
    unittest.main()
