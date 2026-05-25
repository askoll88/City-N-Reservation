import unittest
from unittest.mock import patch

from game.hunting_grounds import (
    HUNT_DURATION_MAX_SECONDS,
    HUNT_DURATION_MIN_SECONDS,
    PALE_WATCHER_ADMIN_FORCE_FLAG,
    PALE_WATCHER_DONE_FLAG,
    PALE_WATCHER_NEXT_OMEN_CHANCE,
    PALE_WATCHER_REQUIRED_OMENS,
    PALE_WATCHER_SCENE_STATE_KEY,
    PALE_WATCHER_START_CHANCE,
    PALE_WATCHER_TRAIL_FLAG,
    TACTICS,
    handle_pale_watcher_scene_callback,
    _finish_pale_watcher_death,
    _finish_pale_watcher_omen,
    _format_menu,
    _format_pale_watcher_omen,
    _format_timer,
    _maybe_handle_pale_watcher,
    _roll_pale_watcher_next_omen,
    _roll_pale_watcher_start,
    start_hunt,
)


class DummyMessages:
    def __init__(self):
        self.sent = []

    def send(self, **kwargs):
        self.sent.append(kwargs)
        return len(self.sent)


class DummyVK:
    def __init__(self):
        self.messages = DummyMessages()


class DummyPlayer:
    user_id = 1901
    current_location_id = "охотничьи_угодья"
    level = 28
    health = 120
    max_health = 120
    energy = 70
    radiation = 0
    money = 10000
    experience = 2000


class NeverRandom:
    def random(self):
        return 1.0


class AlwaysRandom:
    def random(self):
        return 0.0


class HuntingGroundsLegendTests(unittest.TestCase):
    def test_format_timer_under_minute_does_not_round_to_one_minute(self):
        self.assertEqual(_format_timer(59), "59 сек.")
        self.assertEqual(_format_timer(1), "1 сек.")
        self.assertEqual(_format_timer(60), "1 мин. 0 сек.")
        self.assertEqual(_format_timer(125), "2 мин. 5 сек.")

    def test_start_hunt_stores_random_duration_range(self):
        player = DummyPlayer()
        vk = DummyVK()

        with patch("game.hunting_grounds.database.get_runtime_state", return_value=None), \
             patch("game.hunting_grounds.database.get_user_flag", return_value=1), \
             patch("game.hunting_grounds.database.update_user_stats"), \
             patch("game.hunting_grounds.database.set_runtime_state") as set_state:
            handled = start_hunt(player, vk, player.user_id, "ambush")

        self.assertTrue(handled)
        duration = set_state.call_args.args[2]["duration"]
        self.assertGreaterEqual(duration, HUNT_DURATION_MIN_SECONDS)
        self.assertLessEqual(duration, HUNT_DURATION_MAX_SECONDS)
        self.assertIn("Возвращайся к меткам примерно через", vk.messages.sent[-1]["message"])

    def test_pale_watcher_chain_chances(self):
        self.assertLessEqual(PALE_WATCHER_START_CHANCE, 0.00001)
        self.assertEqual(PALE_WATCHER_NEXT_OMEN_CHANCE, 0.25)

        self.assertTrue(_roll_pale_watcher_start(AlwaysRandom(), 0))
        self.assertFalse(_roll_pale_watcher_start(AlwaysRandom(), 1))
        self.assertFalse(_roll_pale_watcher_start(NeverRandom(), 0))

        self.assertFalse(_roll_pale_watcher_next_omen(AlwaysRandom(), 0))
        self.assertTrue(_roll_pale_watcher_next_omen(AlwaysRandom(), 1))
        self.assertFalse(_roll_pale_watcher_next_omen(NeverRandom(), 1))
        self.assertFalse(_roll_pale_watcher_next_omen(AlwaysRandom(), PALE_WATCHER_REQUIRED_OMENS))

    def test_pale_watcher_omen_consumes_hunt_and_increments_trail_without_showing_creature(self):
        player = DummyPlayer()
        vk = DummyVK()

        with patch("game.hunting_grounds.database.set_user_flag") as set_flag, \
             patch("game.hunting_grounds.database.clear_runtime_state") as clear_state, \
             patch("game.hunting_grounds.invalidate_player_cache"):
            handled = _finish_pale_watcher_omen(player, vk, player.user_id, TACTICS["deep"], 2)

        self.assertTrue(handled)
        clear_state.assert_called_once_with(player.user_id, "hunting_grounds_state")
        set_flag.assert_called_once_with(player.user_id, PALE_WATCHER_TRAIL_FLAG, 2)
        message = vk.messages.sent[-1]["message"]
        self.assertIn("Вылазка сорвалась", message)
        self.assertIn("Ты не видишь никого", message)
        self.assertNotIn("Автор", message)
        self.assertNotIn("Долговязый", message)

    def test_pale_watcher_omens_never_show_the_creature_before_death(self):
        for omen_count in range(1, PALE_WATCHER_REQUIRED_OMENS + 1):
            message = _format_pale_watcher_omen(omen_count, TACTICS["ambush"])
            self.assertNotIn("Автор", message)
            self.assertNotIn("Долговязый", message)
            self.assertNotIn("Потом ты видишь его", message)

    def test_pale_watcher_death_starts_inline_scene_without_immediate_penalty(self):
        player = DummyPlayer()
        vk = DummyVK()

        with patch("game.hunting_grounds.database.set_runtime_state") as set_scene, \
             patch("game.hunting_grounds.database.clear_runtime_state") as clear_state, \
             patch("game.hunting_grounds.invalidate_player_cache"):
            handled = _finish_pale_watcher_death(player, vk, player.user_id, TACTICS["deep"])

        self.assertTrue(handled)
        self.assertEqual(len(vk.messages.sent), 1)
        self.assertIn("это уже не охота", vk.messages.sent[0]["message"])
        self.assertIn("keyboard", vk.messages.sent[0])
        self.assertEqual(player.current_location_id, "охотничьи_угодья")
        self.assertEqual(player.money, 10000)
        clear_state.assert_called_once_with(player.user_id, "hunting_grounds_state")
        set_scene.assert_called_once()
        self.assertEqual(set_scene.call_args.args[1], PALE_WATCHER_SCENE_STATE_KEY)
        self.assertEqual(set_scene.call_args.args[2]["step"], 0)
        self.assertEqual(set_scene.call_args.args[2]["tactic"], "deep")

    def test_pale_watcher_scene_reveals_image_then_respawns_in_hospital(self):
        player = DummyPlayer()
        vk = DummyVK()
        scene_state = {"step": 0, "tactic": "deep", "started_at": 10}

        def get_runtime_state(_user_id, key):
            if key == PALE_WATCHER_SCENE_STATE_KEY:
                return scene_state
            return None

        def set_runtime_state(_user_id, key, value):
            if key == PALE_WATCHER_SCENE_STATE_KEY:
                updated = dict(value)
                scene_state.clear()
                scene_state.update(updated)

        with patch("game.hunting_grounds.database.get_runtime_state", side_effect=get_runtime_state), \
             patch("game.hunting_grounds.database.set_runtime_state", side_effect=set_runtime_state), \
             patch("game.hunting_grounds.database.set_user_flag") as set_flag, \
             patch("game.hunting_grounds.database.clear_runtime_state") as clear_state, \
             patch("game.hunting_grounds.database.update_user_location") as update_location, \
             patch("game.hunting_grounds.database.update_user_stats") as update_stats, \
             patch("game.hunting_grounds._upload_pale_watcher_image", return_value="photo1_2") as upload_image, \
             patch("game.hunting_grounds.invalidate_player_cache"):
            self.assertTrue(handle_pale_watcher_scene_callback(player, vk, player.user_id, {"action": "next"}))
            self.assertTrue(handle_pale_watcher_scene_callback(player, vk, player.user_id, {"action": "next"}))
            self.assertTrue(handle_pale_watcher_scene_callback(player, vk, player.user_id, {"action": "next"}))
            self.assertTrue(handle_pale_watcher_scene_callback(player, vk, player.user_id, {"action": "next"}))
            self.assertTrue(handle_pale_watcher_scene_callback(player, vk, player.user_id, {"action": "next"}))

        self.assertGreaterEqual(len(vk.messages.sent), 6)
        self.assertIn("Между деревьями", vk.messages.sent[0]["message"])
        self.assertEqual(vk.messages.sent[0].get("attachment"), "photo1_2")
        self.assertIn("Удар приходит в грудь", vk.messages.sent[-3]["message"])
        self.assertIn("Закрыть глаза", vk.messages.sent[-3].get("keyboard", ""))
        self.assertIn("Ты закрываешь глаза", vk.messages.sent[-2]["message"])
        self.assertIn("Ты погиб", vk.messages.sent[-1]["message"])
        self.assertTrue(all("Автор" not in sent["message"] for sent in vk.messages.sent))
        upload_image.assert_called_once_with(vk, player.user_id)
        self.assertEqual(player.current_location_id, "больница")
        self.assertEqual(player.health, 60)
        self.assertEqual(player.energy, 50)
        self.assertEqual(player.money, 8000)
        self.assertEqual(player.experience, 1700)
        clear_state.assert_any_call(player.user_id, "hunting_grounds_state")
        clear_state.assert_any_call(player.user_id, PALE_WATCHER_SCENE_STATE_KEY)
        set_flag.assert_any_call(player.user_id, PALE_WATCHER_TRAIL_FLAG, 0)
        set_flag.assert_any_call(player.user_id, PALE_WATCHER_DONE_FLAG, 1)
        update_location.assert_called_once_with(player.user_id, "больница")
        update_stats.assert_called_once()

    def test_pale_watcher_done_flag_blocks_future_omens_and_death(self):
        player = DummyPlayer()
        vk = DummyVK()

        def get_flag(_user_id, flag_name, default=0):
            if flag_name == PALE_WATCHER_DONE_FLAG:
                return 1
            if flag_name == PALE_WATCHER_TRAIL_FLAG:
                return PALE_WATCHER_REQUIRED_OMENS
            return default

        with patch("game.hunting_grounds.database.get_user_flag", side_effect=get_flag), \
             patch("game.hunting_grounds._finish_pale_watcher_death") as finish_death, \
             patch("game.hunting_grounds._finish_pale_watcher_omen") as finish_omen:
            handled = _maybe_handle_pale_watcher(
                player,
                vk,
                player.user_id,
                {"seed": 1},
                TACTICS["ambush"],
            )

        self.assertFalse(handled)
        finish_death.assert_not_called()
        finish_omen.assert_not_called()

    def test_pale_watcher_death_is_guaranteed_after_all_omens_if_not_done(self):
        player = DummyPlayer()
        vk = DummyVK()

        def get_flag(_user_id, flag_name, default=0):
            if flag_name == PALE_WATCHER_DONE_FLAG:
                return 0
            if flag_name == PALE_WATCHER_TRAIL_FLAG:
                return PALE_WATCHER_REQUIRED_OMENS
            return default

        with patch("game.hunting_grounds.database.get_user_flag", side_effect=get_flag), \
             patch("game.hunting_grounds._finish_pale_watcher_death", return_value=True) as finish_death:
            handled = _maybe_handle_pale_watcher(
                player,
                vk,
                player.user_id,
                {"seed": 1},
                TACTICS["ambush"],
            )

        self.assertTrue(handled)
        finish_death.assert_called_once_with(player, vk, player.user_id, TACTICS["ambush"])

    def test_pale_watcher_admin_force_advances_chain_only_for_admins(self):
        player = DummyPlayer()
        vk = DummyVK()

        def get_flag(_user_id, flag_name, default=0):
            if flag_name == PALE_WATCHER_ADMIN_FORCE_FLAG:
                return 1
            return default

        with patch("game.hunting_grounds.database.get_user_flag", side_effect=get_flag), \
             patch("game.hunting_grounds.database.is_user_admin", return_value=True), \
             patch("game.hunting_grounds._finish_pale_watcher_omen", return_value=True) as finish_omen:
            handled = _maybe_handle_pale_watcher(
                player,
                vk,
                player.user_id,
                {"seed": 1},
                TACTICS["ambush"],
            )

        self.assertTrue(handled)
        finish_omen.assert_called_once_with(player, vk, player.user_id, TACTICS["ambush"], 1)

        with patch("game.hunting_grounds.database.get_user_flag", side_effect=get_flag), \
             patch("game.hunting_grounds.database.is_user_admin", return_value=False), \
             patch("game.hunting_grounds._finish_pale_watcher_omen") as finish_omen:
            handled = _maybe_handle_pale_watcher(
                player,
                vk,
                player.user_id,
                {"seed": 1},
                TACTICS["ambush"],
            )

        self.assertFalse(handled)
        finish_omen.assert_not_called()

    def test_hunting_menu_shows_plain_omen_notes(self):
        player = DummyPlayer()

        def get_flag(_user_id, flag_name, default=0):
            if flag_name == PALE_WATCHER_TRAIL_FLAG:
                return 2
            return default

        with patch("game.hunting_grounds.database.get_user_flag", side_effect=get_flag):
            message = _format_menu(player, user_id=player.user_id)

        self.assertIn("гильза на пне", message)
        self.assertNotIn("Автор", message)
        self.assertNotIn("ужас", message.lower())


if __name__ == "__main__":
    unittest.main()
