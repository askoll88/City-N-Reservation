import unittest
from unittest.mock import patch

from handlers.commands import handle_navigation, handle_npc_selection
from handlers.keyboards import create_forester_trial_keyboard
from handlers.npc import handle_forester_trial_choice, show_npc_dialog, _handle_forester_unlock_hunting


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
    def __init__(self, location_id="заимка_лесника", level=10):
        self.user_id = 1201
        self.current_location_id = location_id
        self.level = level


class ForesterDialogTests(unittest.TestCase):
    def test_forester_name_is_not_swallowed_by_forest_navigation(self):
        player = DummyPlayer()
        vk = DummyVK()

        handled = handle_navigation(player, vk, player.user_id, "лесник")

        self.assertFalse(handled)
        self.assertEqual(player.current_location_id, "заимка_лесника")
        self.assertEqual(vk.messages.sent, [])

    def test_forester_selection_opens_dialog_at_hut(self):
        player = DummyPlayer()
        vk = DummyVK()

        with patch("handlers.quests.track_quest_talk_npc"):
            handled = handle_npc_selection(player, vk, player.user_id, "лесник")

        self.assertTrue(handled)
        self.assertEqual(len(vk.messages.sent), 1)
        self.assertIn("Лесник", vk.messages.sent[0]["message"])

    def test_forester_comments_on_pale_watcher_omens_plainly(self):
        player = DummyPlayer()
        vk = DummyVK()

        def get_flag(_user_id, flag_name, default=0):
            if flag_name == "forest_hunting_pale_watcher_trail":
                return 2
            return default

        with patch("handlers.npc.database.get_user_flag", side_effect=get_flag), \
             patch("handlers.quests.track_quest_talk_npc"), \
             patch("infra.state_manager.set_dialog_state"):
            show_npc_dialog(player, vk, player.user_id, "лесник")

        message = vk.messages.sent[-1]["message"]
        self.assertIn("Донцем вверх", message)
        self.assertIn("тебя проверяют", message.lower())
        self.assertNotIn("Автор", message)

    def test_forester_remembers_pale_watcher_after_death(self):
        player = DummyPlayer()
        vk = DummyVK()

        def get_flag(_user_id, flag_name, default=0):
            if flag_name == "forest_hunting_pale_watcher_done":
                return 1
            return default

        with patch("handlers.npc.database.get_user_flag", side_effect=get_flag), \
             patch("handlers.quests.track_quest_talk_npc"), \
             patch("infra.state_manager.set_dialog_state"):
            show_npc_dialog(player, vk, player.user_id, "лесник")

        message = vk.messages.sent[-1]["message"]
        self.assertIn("Раз видел его и вернулся", message)
        self.assertIn("второй раз не приходит", message)

    def test_forester_trial_keyboard_does_not_color_hint_answers(self):
        keyboard = create_forester_trial_keyboard("tracks").get_keyboard()

        self.assertIn("Снять слепок следа", keyboard)
        self.assertIn("Проверить кровь", keyboard)
        self.assertIn("Замереть на шум", keyboard)
        for stage in ("tracks", "wind", "bait", "shot", "exit"):
            stage_keyboard = create_forester_trial_keyboard(stage).get_keyboard().lower()
            self.assertNotIn("positive", stage_keyboard)
            self.assertNotIn("primary", stage_keyboard)
        self.assertIn("Ждать разворот", create_forester_trial_keyboard("shot").get_keyboard())
        self.assertIn("Пометить тропу", create_forester_trial_keyboard("exit").get_keyboard())

    def test_forester_trial_intro_reads_like_field_assessment(self):
        player = DummyPlayer()
        vk = DummyVK()

        with patch("handlers.npc.database.get_user_flag", return_value=0), \
             patch("handlers.quests.accept_story_quest"), \
             patch("infra.state_manager.set_dialog_state"):
            handled = _handle_forester_unlock_hunting(player, vk, player.user_id, "лесник")

        self.assertTrue(handled)
        message = vk.messages.sent[-1]["message"]
        self.assertIn("отпечаток копыта", message)
        self.assertIn("С чего начинаешь разбор", message)
        self.assertNotIn("красивого ответа", message)

    def test_forester_trial_tracks_step_scores_and_explains_order(self):
        player = DummyPlayer()
        vk = DummyVK()

        with patch("infra.state_manager.set_dialog_state") as set_state:
            handled = handle_forester_trial_choice(player, vk, player.user_id, "Проверить кровь", "forester_trial:tracks:0")

        self.assertTrue(handled)
        set_state.assert_called_once_with(player.user_id, "лесник", "forester_trial:wind:1")
        self.assertIn("хуже следа", vk.messages.sent[-1]["message"])
        self.assertIn("солонец стоит в низине", vk.messages.sent[-1]["message"])

    def test_forester_trial_continues_from_bait_to_shot(self):
        player = DummyPlayer()
        vk = DummyVK()

        with patch("infra.state_manager.set_dialog_state") as set_state:
            handled = handle_forester_trial_choice(player, vk, player.user_id, "Осмотреть периметр", "forester_trial:bait:3")

        self.assertTrue(handled)
        set_state.assert_called_once_with(player.user_id, "лесник", "forester_trial:shot:5")
        self.assertIn("Проверка четвёртая", vk.messages.sent[-1]["message"])

    def test_forester_trial_continues_from_shot_to_exit(self):
        player = DummyPlayer()
        vk = DummyVK()

        with patch("infra.state_manager.set_dialog_state") as set_state:
            handled = handle_forester_trial_choice(player, vk, player.user_id, "Сместиться ниже", "forester_trial:shot:5")

        self.assertTrue(handled)
        set_state.assert_called_once_with(player.user_id, "лесник", "forester_trial:exit:6")
        self.assertIn("Проверка пятая", vk.messages.sent[-1]["message"])

    def test_forester_trial_allows_imperfect_but_safe_route(self):
        player = DummyPlayer()
        vk = DummyVK()

        with patch("handlers.npc.database.set_user_flag") as set_flag, \
             patch("handlers.quests.complete_story_quest"), \
             patch("infra.state_manager.set_dialog_state"):
            handled = handle_forester_trial_choice(player, vk, player.user_id, "Пометить тропу", "forester_trial:exit:6")

        self.assertTrue(handled)
        self.assertTrue(set_flag.called)
        self.assertIn("Открыт маршрут", vk.messages.sent[-1]["message"])

    def test_forester_trial_rejects_low_score_after_five_steps(self):
        player = DummyPlayer()
        vk = DummyVK()

        with patch("handlers.npc.database.set_user_flag") as set_flag, \
             patch("infra.state_manager.set_dialog_state"):
            handled = handle_forester_trial_choice(player, vk, player.user_id, "Добрать сразу", "forester_trial:exit:6")

        self.assertTrue(handled)
        set_flag.assert_not_called()
        self.assertIn("путаешь порядок", vk.messages.sent[-1]["message"])


if __name__ == "__main__":
    unittest.main()
