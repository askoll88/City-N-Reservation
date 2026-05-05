import unittest
from unittest.mock import patch

from handlers.combat import handle_combat_attack
from infra.state_manager import clear_combat_state, set_combat_state, set_ui_message, invalidate_edit_targets
from game.weapon_dungeons import (
    DUNGEON_ENERGY_COST,
    DUNGEON_WAVES,
    format_warehouse17_menu,
    get_available_warehouse17_threats,
    grant_warehouse17_rewards,
    start_warehouse17_run,
)


class DummyPlayer:
    def __init__(self, rank_tier=1, energy=100):
        self.rank_tier = rank_tier
        self.energy = energy

    def _get_rank_tier(self):
        return self.rank_tier


class DummyCombatInventory:
    weapons = []

    def reload(self):
        return None


class DummyCombatPlayer:
    current_location_id = "склад_17"
    level = 5
    health = 100
    max_health = 100
    energy = 80
    max_energy = 100
    equipped_weapon = None
    inventory = DummyCombatInventory()
    melee_damage = 50
    crit_chance = 0
    crit_damage = 0
    dodge_chance = 0
    total_defense = 0
    luck = 1
    effective_luck = 1
    effective_stamina = 1
    player_class = None

    def _get_passive_bonuses(self):
        return {}


class DummyMessages:
    def __init__(self):
        self.sent = []
        self.edited = []

    def send(self, **kwargs):
        self.sent.append(kwargs)
        return 901

    def edit(self, **kwargs):
        self.edited.append(kwargs)
        return 1


class DummyVk:
    def __init__(self):
        self.messages = DummyMessages()


class WeaponDungeonsTest(unittest.TestCase):
    def tearDown(self):
        clear_combat_state(777)
        invalidate_edit_targets(777)

    def test_available_threats_follow_rank_weapon_progression(self):
        self.assertEqual([t.id for t in get_available_warehouse17_threats(1)], ["i"])
        self.assertEqual([t.id for t in get_available_warehouse17_threats(8)], ["i", "ii", "iii"])
        self.assertEqual([t.id for t in get_available_warehouse17_threats(24)], ["i", "ii", "iii", "iv", "v"])

    def test_menu_mentions_energy_and_three_waves(self):
        menu = format_warehouse17_menu(DummyPlayer(rank_tier=1, energy=100))
        self.assertIn(str(DUNGEON_ENERGY_COST), menu)
        self.assertIn(str(DUNGEON_WAVES), menu)
        self.assertIn("Угроза I", menu)

    def test_start_run_spends_energy_and_starts_combat(self):
        player = DummyPlayer(rank_tier=24, energy=100)
        with patch("game.weapon_dungeons.database.update_user_stats") as update_stats, \
             patch("handlers.combat.start_dungeon_combat", return_value=True) as start_combat:
            result = start_warehouse17_run(player, object(), 777, "угроза v")

        self.assertTrue(result["success"])
        self.assertEqual(player.energy, 60)
        update_stats.assert_called_once_with(777, energy=60)
        dungeon_run = start_combat.call_args.args[3]
        self.assertEqual(dungeon_run["wave"], 1)
        self.assertEqual(dungeon_run["waves_total"], 3)
        self.assertEqual(dungeon_run["threat_id"], "v")

    def test_rewards_are_granted_as_weapon_materials(self):
        with patch("game.weapon_dungeons.random.randint", return_value=1), \
             patch("game.weapon_dungeons.database.add_weapon_material", return_value=True) as add_material:
            rewards = grant_warehouse17_rewards(777, "v")

        names = {name for name, _qty in rewards}
        self.assertIn("Ядро оружейного резонанса", names)
        self.assertTrue(add_material.called)

    def test_wave_victory_keeps_combat_edit_target_on_next_wave(self):
        vk = DummyVk()
        set_ui_message(777, "combat", 55, peer_id=777)
        set_combat_state(777, {
            "combat_id": "wave-1",
            "enemy_name": "Складской зомби",
            "enemy_hp": 1,
            "enemy_max_hp": 20,
            "enemy_damage": 1,
            "enemy_level": 6,
            "enemy_role_label": "Танк",
            "enemy_evade_chance": 0,
            "turn": "player",
            "dungeon_run": {
                "id": "склад_17",
                "name": "Оружейный бункер «Склад 17»",
                "threat_id": "i",
                "threat_label": "Угроза I",
                "wave": 1,
                "waves_total": 3,
                "enemy_level": 6,
                "reward_mult": 1.0,
            },
        })
        next_combat = {
            "combat_id": "wave-2",
            "enemy_name": "Бункерный мародёр",
            "enemy_hp": 20,
            "enemy_max_hp": 20,
            "enemy_damage": 1,
            "enemy_level": 8,
            "enemy_role_label": "Контролёр",
            "turn": "player",
            "dungeon_run": {"wave": 2},
        }

        with patch("handlers.combat.database.update_user_stats"), \
             patch("handlers.combat.random.randint", return_value=100), \
             patch("handlers.combat._build_dungeon_wave", return_value=(next_combat, "NEXT WAVE SCREEN")):
            handle_combat_attack(DummyCombatPlayer(), vk, 777)

        self.assertEqual(vk.messages.sent, [])
        self.assertEqual(len(vk.messages.edited), 1)
        edited = vk.messages.edited[0]
        self.assertEqual(edited["message_id"], 55)
        self.assertIn("ВОЛНА ПРОЙДЕНА", edited["message"])
        self.assertIn("NEXT WAVE SCREEN", edited["message"])
        self.assertIn("wave-2", edited["keyboard"])


if __name__ == "__main__":
    unittest.main()
