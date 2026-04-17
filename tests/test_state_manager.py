import time
import unittest

import infra.state_manager as state_manager


class StateManagerTest(unittest.TestCase):
    def setUp(self):
        state_manager.get_combat_state().clear()
        state_manager.get_dialog_state().clear()
        state_manager.get_research_state().clear()
        state_manager.get_anomaly_state().clear()
        state_manager.invalidate_player_cache()

    def test_combat_state_roundtrip(self):
        user_id = 101
        payload = {"enemy": "бандит", "hp": 50}

        state_manager.set_combat_state(user_id, payload)
        self.assertTrue(state_manager.is_in_combat(user_id))
        self.assertEqual(state_manager.get_combat_data(user_id), payload)

        state_manager.clear_combat_state(user_id)
        self.assertFalse(state_manager.is_in_combat(user_id))

    def test_player_cache_roundtrip(self):
        user_id = 202
        player_obj = {"id": user_id}

        state_manager.cache_player(user_id, player_obj)
        cached = state_manager.get_cached_player(user_id)

        self.assertEqual(cached, player_obj)
        self.assertEqual(state_manager.get_cached_players_count(), 1)

    def test_cleanup_inactive_states(self):
        now = time.time()
        state_manager.get_research_state()[1] = {"start_time": now - 1000, "duration": 300}
        state_manager.get_combat_state()[2] = {"start_time": now - 1000}

        removed = state_manager.cleanup_inactive_states(max_idle_seconds=300)

        self.assertEqual(removed, 2)
        self.assertNotIn(1, state_manager.get_research_state())
        self.assertNotIn(2, state_manager.get_combat_state())


if __name__ == "__main__":
    unittest.main()
