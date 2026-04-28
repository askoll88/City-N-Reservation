import unittest

from handlers import location


class RandomEventFrequencyTests(unittest.TestCase):
    def test_spawn_state_after_cooldown_has_meaningful_chance(self):
        now = 10_000
        last_event = now - location.EVENT_COOLDOWN_SECONDS

        state = location.get_event_spawn_state(last_event, now=now)

        self.assertTrue(state["ready"])
        self.assertEqual(state["cooldown_remaining"], 0)
        self.assertGreaterEqual(state["chance"], 45.0)

    def test_spawn_state_ramps_to_max_after_waiting(self):
        now = 20_000
        last_event = now - location.EVENT_COOLDOWN_SECONDS - 8 * location.EVENT_CHANCE_RAMP_UP

        state = location.get_event_spawn_state(last_event, now=now)

        self.assertEqual(state["chance"], 100.0)

    def test_travel_event_outer_roll_is_not_tiny(self):
        self.assertGreaterEqual(location.TRAVEL_EVENT_CHANCE, 25)
        self.assertGreaterEqual(location.TRAVEL_EVENT_CHANCE_FORCED, 40)


if __name__ == "__main__":
    unittest.main()
