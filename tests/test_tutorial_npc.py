import json
import unittest
from unittest.mock import patch

from game.tutorial import (
    TUTORIAL_SECTIONS,
    create_tutorial_home_keyboard,
    format_tutorial_page,
)
from handlers.commands import handle_npc_selection
from handlers.keyboards import create_npc_dialog_keyboard
from handlers.npc import _handle_medic_supply, show_npc_dialog
from models.npcs import get_npc


class DummyMessages:
    def __init__(self):
        self.sent = []
        self.edited = []

    def send(self, **kwargs):
        self.sent.append(kwargs)
        return len(self.sent)

    def edit(self, **kwargs):
        self.edited.append(kwargs)
        return 1


class DummyVK:
    def __init__(self):
        self.messages = DummyMessages()


class DummyPlayer:
    current_location_id = "убежище"
    level = 1


class DummyInventory:
    def reload(self):
        pass


class DummyMedicPlayer:
    current_location_id = "больница"
    level = 28
    energy = 124
    max_energy = 100
    inventory = DummyInventory()


class TutorialNpcTest(unittest.TestCase):
    def setUp(self):
        self.vk = DummyVK()
        self.player = DummyPlayer()

    def test_guide_replaces_local_resident_as_tutorial_npc(self):
        npc = get_npc("местный житель")

        self.assertEqual(npc.name, "Старый проводник")
        self.assertIn("обучениебой", npc.get_menu())
        self.assertIn("обучениересурсы", npc.get_menu())
        self.assertEqual(npc.get_question_text("обучениестаты"), "Статы")

    def test_tutorial_sections_cover_core_mechanics(self):
        expected = {"basics", "combat", "resources", "stats", "gear", "anomalies", "economy", "events"}

        self.assertEqual(set(TUTORIAL_SECTIONS), expected)
        for section_id in expected:
            message, page, total_pages = format_tutorial_page(section_id, 0)
            self.assertEqual(page, 0)
            self.assertGreaterEqual(total_pages, 3)
            self.assertIn("ОБУЧЕНИЕ", message)

    def test_guide_keyboard_fits_two_buttons_per_row(self):
        keyboard = json.loads(create_npc_dialog_keyboard("местный житель").get_keyboard())

        self.assertLessEqual(len(keyboard["buttons"]), 6)
        self.assertEqual(keyboard["buttons"][0][0]["action"]["label"], "Маршрут и меню")
        self.assertEqual(keyboard["buttons"][0][1]["action"]["label"], "Бои")

    def test_tutorial_home_keyboard_uses_callbacks(self):
        keyboard = json.loads(create_tutorial_home_keyboard().get_keyboard())
        first_payload = json.loads(keyboard["buttons"][0][0]["action"]["payload"])

        self.assertTrue(keyboard["inline"])
        self.assertEqual(first_payload["command"], "tutorial_page")
        self.assertEqual(first_payload["section"], "basics")

    def test_selecting_tutorial_section_opens_paged_ui(self):
        with patch("game.tutorial.try_edit_or_send_ui") as send_ui:
            show_npc_dialog(self.player, self.vk, 1001, "местный житель", "обучениебой")

        send_ui.assert_called_once()
        args, kwargs = send_ui.call_args
        self.assertEqual(args[2], "tutorial")
        self.assertIn("ОБУЧЕНИЕ: БОИ", args[3])

    def test_guide_selection_alias_opens_local_resident_key(self):
        handled = handle_npc_selection(self.player, self.vk, 1002, "проводник")

        self.assertTrue(handled)
        self.assertIn("Старый проводник", self.vk.messages.sent[0]["message"])

    def test_medic_supply_does_not_cut_overcap_energy(self):
        player = DummyMedicPlayer()

        with patch("handlers.npc.database.get_user_flag", return_value=0), \
             patch("handlers.npc.database.update_user_stats") as update_stats, \
             patch("handlers.npc.database.add_item_to_inventory", return_value=True), \
             patch("handlers.npc.database.set_user_flag"):
            handled = _handle_medic_supply(player, self.vk, 1003, "медик")

        self.assertTrue(handled)
        self.assertEqual(player.energy, 124)
        update_stats.assert_called_once_with(1003, energy=124)
        self.assertIn("Энергия: 124 → 124", self.vk.messages.sent[-1]["message"])


if __name__ == "__main__":
    unittest.main()
