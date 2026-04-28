import unittest
import logging

from infra import state_manager, vk_messages


class _Keyboard:
    def get_keyboard(self):
        return '{"buttons":[]}'


class _Messages:
    def __init__(self):
        self.sent = []
        self.edited = []
        self.answered = []
        self.fail_first_send = False

    def send(self, **kwargs):
        self.sent.append(kwargs)
        if self.fail_first_send and len(self.sent) == 1:
            raise RuntimeError("attachment failed")
        return 101

    def edit(self, **kwargs):
        self.edited.append(kwargs)
        return 1

    def send_message_event_answer(self, **kwargs):
        self.answered.append(kwargs)
        return 1


class _Vk:
    def __init__(self):
        self.messages = _Messages()


class VkMessagesTests(unittest.TestCase):
    def test_send_adds_safe_defaults_and_keyboard_payload(self):
        vk = _Vk()

        msg_id = vk_messages.send(vk, user_id=7, message="hello @all", keyboard=_Keyboard())

        self.assertEqual(msg_id, 101)
        sent = vk.messages.sent[0]
        self.assertEqual(sent["user_id"], 7)
        self.assertEqual(sent["message"], "hello @all")
        self.assertEqual(sent["keyboard"], '{"buttons":[]}')
        self.assertEqual(sent["random_id"], 0)
        self.assertEqual(sent["disable_mentions"], 1)
        self.assertEqual(sent["dont_parse_links"], 1)

    def test_send_retries_without_attachment(self):
        vk = _Vk()
        vk.messages.fail_first_send = True

        logging.disable(logging.CRITICAL)
        try:
            vk_messages.send(vk, user_id=7, message="loc", attachment="photo1_2")
        finally:
            logging.disable(logging.NOTSET)

        self.assertEqual(len(vk.messages.sent), 2)
        self.assertEqual(vk.messages.sent[0]["attachment"], "photo1_2")
        self.assertNotIn("attachment", vk.messages.sent[1])
        self.assertEqual(vk.messages.sent[1]["disable_mentions"], 1)
        self.assertEqual(vk.messages.sent[1]["dont_parse_links"], 1)

    def test_state_manager_edit_or_send_uses_safe_transport(self):
        vk = _Vk()
        state_manager.set_last_message(42, 5)

        state_manager.try_edit_or_send(vk, 42, "screen", keyboard=_Keyboard())

        self.assertEqual(len(vk.messages.edited), 1)
        edited = vk.messages.edited[0]
        self.assertEqual(edited["peer_id"], 42)
        self.assertEqual(edited["message_id"], 5)
        self.assertEqual(edited["message"], "screen")
        self.assertEqual(edited["disable_mentions"], 1)
        self.assertEqual(edited["dont_parse_links"], 1)

    def test_answer_event_can_send_snackbar_payload(self):
        vk = _Vk()

        vk_messages.answer_event(
            vk,
            event_id="evt",
            user_id=7,
            peer_id=7,
            text="Готово",
            show_snackbar=True,
        )

        answered = vk.messages.answered[0]
        self.assertEqual(answered["event_id"], "evt")
        self.assertIn('"type": "show_snackbar"', answered["event_data"])
        self.assertIn('"text": "Готово"', answered["event_data"])


if __name__ == "__main__":
    unittest.main()
