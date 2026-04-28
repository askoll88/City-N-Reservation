import unittest
from unittest.mock import patch

from game.location_mechanics import (
    REGION_GAMEPLAY_LOOPS,
    apply_region_loop_event,
    check_ambush,
    check_mutant_hunt,
    check_zone_mutation,
    format_region_loop_status,
    get_region_loop_config,
    get_region_loop_event_weights,
    get_region_loop_state,
    reset_region_loop_state,
)
from game.constants import RESEARCH_LOCATIONS
from handlers.combat import _apply_region_loop_rewards, _build_research_modifiers_info
from infra.state_manager import clear_combat_state, set_combat_state


class LoopStorage:
    def __init__(self):
        self.values = {}

    def get_user_flag(self, user_id, flag_name, default=0):
        return self.values.get((user_id, flag_name), default)

    def set_user_flag(self, user_id, flag_name, value):
        self.values[(user_id, flag_name)] = int(value)


class RegionGameplayLoopTests(unittest.TestCase):
    def setUp(self):
        self.storage = LoopStorage()
        self.get_patch = patch("game.location_mechanics.database.get_user_flag", self.storage.get_user_flag)
        self.set_patch = patch("game.location_mechanics.database.set_user_flag", self.storage.set_user_flag)
        self.get_patch.start()
        self.set_patch.start()

    def tearDown(self):
        self.set_patch.stop()
        self.get_patch.stop()
        clear_combat_state(99)

    def test_each_current_research_branch_has_gameplay_loop(self):
        self.assertEqual(set(REGION_GAMEPLAY_LOOPS.keys()), set(RESEARCH_LOCATIONS))
        for location_id in RESEARCH_LOCATIONS:
            config = get_region_loop_config(location_id)
            self.assertIsNotNone(config)
            self.assertIn("event_deltas", config)
            self.assertIn("pressure_weights", config)
            self.assertIsNotNone(format_region_loop_status(1, location_id))

    def test_military_alert_accumulates_and_can_force_ambush(self):
        user_id = 10
        apply_region_loop_event(user_id, "дорога_военная_часть", "military")
        state = get_region_loop_state(user_id, "дорога_военная_часть")
        self.assertEqual(state["alert"], 18)

        for _ in range(6):
            result = apply_region_loop_event(user_id, "дорога_военная_часть", "trap")

        self.assertTrue(result["effects"].get("forced_ambush"))
        self.assertEqual(result["override_event"], "military")
        self.assertIn("Тревога", "\n".join(result["messages"]))

    def test_nii_data_loop_creates_breakthrough_every_three_packets(self):
        user_id = 11
        first = apply_region_loop_event(user_id, "дорога_нии", "field_lab_data")
        second = apply_region_loop_event(user_id, "дорога_нии", "field_lab_data")
        third = apply_region_loop_event(user_id, "дорога_нии", "field_lab_data")

        self.assertFalse(first["effects"].get("science_breakthrough"))
        self.assertFalse(second["effects"].get("science_breakthrough"))
        self.assertTrue(third["effects"].get("science_breakthrough"))
        self.assertEqual(get_region_loop_state(user_id, "дорога_нии")["data"], 0)

    def test_forest_trail_can_turn_quiet_search_into_hunt(self):
        user_id = 12
        for _ in range(5):
            result = apply_region_loop_event(user_id, "дорога_зараженный_лес", "blood_trail")

        self.assertTrue(result["effects"].get("force_hunt"))
        self.assertEqual(result["override_event"], "mutant")
        self.assertIn("охоту", "\n".join(result["messages"]))

    def test_loop_state_changes_next_event_weights(self):
        user_id = 13
        apply_region_loop_event(user_id, "дорога_зараженный_лес", "blood_trail")
        weights = get_region_loop_event_weights(user_id, "дорога_зараженный_лес")

        self.assertGreater(weights["mutant"], 1.0)
        self.assertGreater(weights["blood_trail"], 1.0)

    def test_pressure_increases_unique_mechanic_chances_when_user_state_exists(self):
        user_id = 14
        for _ in range(6):
            apply_region_loop_event(user_id, "дорога_военная_часть", "military")
        with patch("game.location_mechanics.random.random", return_value=0.10):
            self.assertFalse(check_ambush("дорога_военная_часть"))
            self.assertTrue(check_ambush("дорога_военная_часть", user_id=user_id))

        reset_region_loop_state(user_id, "дорога_нии")
        for _ in range(5):
            apply_region_loop_event(user_id, "дорога_нии", "anomaly")
        with patch("game.location_mechanics.random.random", return_value=0.12):
            self.assertTrue(check_zone_mutation("дорога_нии", user_id=user_id))

        for _ in range(5):
            apply_region_loop_event(user_id, "дорога_зараженный_лес", "blood_trail")
        with patch("game.location_mechanics.random.random", return_value=0.18):
            self.assertTrue(check_mutant_hunt(user_id=user_id))

    def test_research_modifier_text_includes_region_loop_status(self):
        user_id = 15
        apply_region_loop_event(user_id, "дорога_военная_часть", "military")
        _, text = _build_research_modifiers_info("дорога_военная_часть", 10, user_id=user_id)

        self.assertIn("Состояние ветки", text)
        self.assertIn("Тревога патрулей", text)

    def test_region_loop_rewards_do_not_interrupt_active_combat(self):
        class DummyMessages:
            def __init__(self):
                self.sent = []

            def send(self, **kwargs):
                self.sent.append(kwargs)

        class DummyVk:
            def __init__(self):
                self.messages = DummyMessages()

        set_combat_state(99, {"combat_id": "active"})
        vk = DummyVk()
        loop_result = {"effects": {"organic_trophy": True, "science_breakthrough": True}}

        _apply_region_loop_rewards(object(), vk, 99, "дорога_зараженный_лес", loop_result)

        self.assertEqual(vk.messages.sent, [])


if __name__ == "__main__":
    unittest.main()
