import json
import time
import unittest
from unittest.mock import patch

from game import limited_events


class LimitedEventsTests(unittest.TestCase):
    def setUp(self):
        limited_events._cache["at"] = 0.0
        limited_events._cache["state"] = None

    def test_active_event_is_scoped_to_location_branch(self):
        state = {
            "schedule_version": 2,
            "active_event_id": "anomaly_surge",
            "active_scope_id": "science",
            "active_start_ts": int(time.time()) - 60,
            "active_end_ts": int(time.time()) + 3600,
            "next_event_id": "predator_night",
            "next_scope_id": "forest",
            "next_start_ts": int(time.time()) + 7200,
            "announce_sent": False,
        }

        with patch("game.limited_events.database.get_game_setting", return_value=json.dumps(state)):
            science_event = limited_events.get_active_limited_event("дорога_нии")
            military_event = limited_events.get_active_limited_event("дорога_военная_часть")
            science_mods = limited_events.get_limited_event_modifiers("главный_корпус_нии")
            military_mods = limited_events.get_limited_event_modifiers("военная_часть")

        self.assertIsNotNone(science_event)
        self.assertEqual(science_event["scope_id"], "science")
        self.assertIsNone(military_event)
        self.assertGreater(science_mods["artifact_event_mult"], 1.0)
        self.assertEqual(military_mods["artifact_event_mult"], 1.0)


if __name__ == "__main__":
    unittest.main()
