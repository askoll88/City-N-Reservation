import json
import unittest
from unittest.mock import patch

from handlers.keyboards import create_status_keyboard
from handlers.status import STATUS_PAGES, format_status_page


class DummyInventory:
    total_weight = 12.5

    def __init__(self):
        self.weapons = [
            {
                "name": "АК-74 «Резонанс»",
                "attack": 120,
                "item_level": 20,
                "weapon_cap": 20,
                "weapon_ascension": 1,
                "item_rank": "legendary",
                "event_bonus_name": "Стабилизатор резонанса",
                "event_bonus_text": "Крит. шанс +5%",
            }
        ]

    def reload(self):
        return None


class DummyLocation:
    name = "Убежище"


class DummyPlayer:
    user_id = 777
    level = 7
    LEVELS = {1: 0, 2: 100, 3: 250, 4: 450, 5: 700, 6: 1000, 7: 1400, 8: 1900}
    MAX_LEVEL = 20
    experience = 1400
    health = 88
    max_health = 120
    energy = 64
    max_energy = 100
    radiation = 8
    money = 1234
    player_class = "следопыт"
    equipped_weapon = "АК-74 «Резонанс»"
    equipped_backpack = "Рюкзак"
    equipped_device = "Детектор"
    inventory = DummyInventory()
    max_weight = 40
    artifact_slots = 2
    equipped_artifacts = ["Капля"]
    effective_strength = 4
    effective_stamina = 6
    effective_perception = 5
    effective_luck = 7
    max_health_bonus = 0
    melee_damage = 12
    total_defense = 18
    crit_chance = 14
    crit_damage = 20
    dodge_chance = 9
    damage_resist = 0
    find_chance = 12
    rare_find_chance = 4

    @property
    def location(self):
        return DummyLocation()

    def get_rank_name(self):
        return "Ходок"

    def get_rank_progress_block(self):
        return "Ранг: 1/24"

    def _is_rank_xp_locked(self):
        return False

    def _get_passive_bonuses(self):
        return {"crit_chance": 3, "travel_time_reduction_pct": 5}


class StatusScreenTest(unittest.TestCase):
    def test_status_keyboard_uses_callback_pagination(self):
        keyboard = create_status_keyboard(page=0, total_pages=len(STATUS_PAGES)).get_keyboard()
        buttons = json.loads(keyboard)["buttons"][0]
        payloads = [json.loads(button["action"]["payload"]) for button in buttons]

        self.assertEqual(buttons[0]["action"]["type"], "callback")
        self.assertEqual(payloads[0], {"command": "status_page", "page": len(STATUS_PAGES) - 1})
        self.assertEqual(payloads[1], {"command": "status_page", "page": 0})
        self.assertEqual(payloads[2], {"command": "status_page", "page": 1})

    def test_status_pages_are_split_by_topic(self):
        with patch("handlers.status.database.get_user_by_vk", return_value={
            "level": 7,
            "experience": 1400,
            "health": 88,
            "energy": 64,
            "radiation": 8,
            "money": 1234,
            "equipped_weapon": "АК-74 «Резонанс»",
            "equipped_backpack": "Рюкзак",
            "equipped_device": "Детектор",
        }), patch("handlers.status.database.get_shells_info", return_value={
            "current": 10,
            "capacity": 20,
            "equipped_bag": "Мешочек",
        }), patch("handlers.status.database.get_user_flag", return_value=0), \
             patch("handlers.status.database.get_item_by_name", return_value=None), \
             patch("handlers.status.database.update_user_stats"):
            overview = format_status_page(DummyPlayer(), 777, 0)
            stats = format_status_page(DummyPlayer(), 777, 2)
            gear = format_status_page(DummyPlayer(), 777, 3)

        self.assertIn("СТАТУС: ОБЩЕЕ", overview)
        self.assertIn("БОЕГОТОВНОСТЬ", overview)
        self.assertIn("СТАТУС: ХАРАКТЕРИСТИКИ", stats)
        self.assertIn("ПРОИЗВОДНЫЕ", stats)
        self.assertIn("СТАТУС: СНАРЯЖЕНИЕ", gear)
        self.assertIn("Стабилизатор резонанса", gear)


if __name__ == "__main__":
    unittest.main()
