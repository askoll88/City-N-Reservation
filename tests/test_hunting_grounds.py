import unittest
from unittest.mock import patch

from game.hunting_grounds import (
    PALE_WATCHER_ADMIN_FORCE_FLAG,
    PALE_WATCHER_DONE_FLAG,
    PALE_WATCHER_NEXT_OMEN_CHANCE,
    PALE_WATCHER_REQUIRED_OMENS,
    PALE_WATCHER_START_CHANCE,
    PALE_WATCHER_TRAIL_FLAG,
    TACTICS,
    _finish_pale_watcher_death,
    _finish_pale_watcher_omen,
    _format_menu,
    _format_pale_watcher_omen,
    _maybe_handle_pale_watcher,
    _roll_pale_watcher_next_omen,
    _roll_pale_watcher_start,
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
        self.assertIn("Охота сорвалась", message)
        self.assertIn("Ты не видишь никого", message)
        self.assertNotIn("Автор", message)
        self.assertNotIn("Долговязый", message)

    def test_pale_watcher_omens_never_show_the_creature_before_death(self):
        for omen_count in range(1, PALE_WATCHER_REQUIRED_OMENS + 1):
            message = _format_pale_watcher_omen(omen_count, TACTICS["ambush"])
            self.assertNotIn("Автор", message)
            self.assertNotIn("Долговязый", message)
            self.assertNotIn("Потом ты видишь его", message)

    def test_pale_watcher_death_is_personal_horror_scene_and_respawns_in_hospital(self):
        player = DummyPlayer()
        vk = DummyVK()

        with patch("game.hunting_grounds.database.set_user_flag") as set_flag, \
             patch("game.hunting_grounds.database.clear_runtime_state") as clear_state, \
             patch("game.hunting_grounds.database.update_user_location") as update_location, \
             patch("game.hunting_grounds.database.update_user_stats") as update_stats, \
             patch("game.hunting_grounds._upload_pale_watcher_image", return_value="photo1_2") as upload_image, \
             patch("game.hunting_grounds.invalidate_player_cache"):
            handled = _finish_pale_watcher_death(player, vk, player.user_id, TACTICS["deep"])

        self.assertTrue(handled)
        self.assertGreaterEqual(len(vk.messages.sent), 4)
        self.assertIn("Долговязый", vk.messages.sent[1]["message"])
        self.assertEqual(vk.messages.sent[1].get("attachment"), "photo1_2")
        self.assertNotIn("attachment", vk.messages.sent[-1])
        self.assertIn("Ты погиб", vk.messages.sent[-1]["message"])
        self.assertTrue(all("Автор" not in sent["message"] for sent in vk.messages.sent))
        upload_image.assert_called_once_with(vk, player.user_id)
        self.assertEqual(player.current_location_id, "больница")
        self.assertEqual(player.health, 60)
        self.assertEqual(player.energy, 50)
        self.assertEqual(player.money, 8000)
        self.assertEqual(player.experience, 1700)
        clear_state.assert_called_once_with(player.user_id, "hunting_grounds_state")
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
