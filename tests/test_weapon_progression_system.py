import unittest

from game.weapon_progression import (
    ASCENSION_CAPS,
    ASCENSION_COSTS,
    ASCENSION_MATERIALS,
    MAX_WEAPON_LEVEL,
    WEAPON_MATERIALS,
    calc_weapon_attack,
    get_event_weapon_bonus,
    get_rank_ascension_limit,
    get_rank_weapon_level_cap,
    get_required_rank_for_ascension,
    get_weapon_cap,
    weapon_level_from_total_xp,
    weapon_total_xp_for_level,
)
from game.item_pool import ITEMS_POOL


class WeaponProgressionSystemTest(unittest.TestCase):
    def test_caps_reach_297_through_ten_ascensions(self):
        self.assertEqual(ASCENSION_CAPS, [10, 20, 40, 60, 90, 120, 150, 180, 210, 250, 297])
        self.assertEqual(get_weapon_cap(0), 10)
        self.assertEqual(get_weapon_cap(10), MAX_WEAPON_LEVEL)

    def test_high_rank_allows_new_weapon_to_be_raised_to_rank_range(self):
        self.assertEqual(get_rank_ascension_limit(1), 0)
        self.assertEqual(get_rank_weapon_level_cap(1), 10)
        self.assertEqual(get_rank_ascension_limit(19), 9)
        self.assertEqual(get_rank_weapon_level_cap(19), 250)
        self.assertEqual(get_rank_ascension_limit(24), 10)
        self.assertEqual(get_rank_weapon_level_cap(24), 297)

    def test_required_rank_for_ascension_matches_unlock_table(self):
        self.assertEqual(get_required_rank_for_ascension(1), 2)
        self.assertEqual(get_required_rank_for_ascension(4), 8)
        self.assertEqual(get_required_rank_for_ascension(10), 24)

    def test_weapon_xp_level_conversion_respects_cap(self):
        total = weapon_total_xp_for_level(40)
        level, overflow = weapon_level_from_total_xp(total + 999999, cap=20)
        self.assertEqual(level, 20)
        self.assertEqual(overflow, 0)

    def test_ascensions_use_four_shared_breakthrough_materials(self):
        self.assertEqual(
            ASCENSION_MATERIALS,
            {
                "Резонансная пластина",
                "Армейский калибровочный набор",
                "Закалённый ствол",
                "Ядро оружейного резонанса",
            },
        )
        used = {material for costs in ASCENSION_COSTS.values() for material in costs}
        self.assertEqual(used, ASCENSION_MATERIALS)
        self.assertEqual(len(ASCENSION_COSTS), 10)

    def test_weapon_material_templates_have_no_weight(self):
        pool_by_name = {row[0]: row for row in ITEMS_POOL}
        for material_name in WEAPON_MATERIALS:
            self.assertIn(material_name, pool_by_name)
            self.assertEqual(pool_by_name[material_name][6], 0.0)

    def test_weapon_attack_uses_base_atk_and_percent_progress(self):
        weapon = {"name": "АК-74", "category": "weapons", "attack": 40, "rarity": "common"}
        level_1 = calc_weapon_attack(weapon, 1, "common", 0)
        level_120 = calc_weapon_attack(weapon, 120, "common", 0)
        self.assertGreater(level_1, 0)
        self.assertGreater(level_120, level_1)
        self.assertEqual(level_120, calc_weapon_attack(weapon, 120, "common", 5))

    def test_weapon_without_attack_gets_default_base_atk(self):
        weapon = {"name": "Самодельный автомат", "category": "weapons", "attack": 0, "rarity": "common"}
        self.assertGreater(calc_weapon_attack(weapon, 1, "common", 0), 0)

    def test_event_weapon_bonus_stats_scale_with_progress(self):
        weapon = {"name": "АК-74 «Резонанс»", "category": "weapons", "attack": 145, "rarity": "legendary"}
        early = get_event_weapon_bonus(weapon, 1, 0)
        leveled_without_ascension = get_event_weapon_bonus(weapon, 250, 0)
        late = get_event_weapon_bonus(weapon, 297, 10)
        self.assertEqual(early["name"], "Стабилизатор резонанса")
        self.assertEqual(early["stats"]["crit_chance"], 4)
        self.assertEqual(leveled_without_ascension["stats"]["crit_chance"], 4)
        self.assertEqual(late["stats"]["crit_chance"], 18)

    def test_ak74_resonance_has_exact_max_attack_target(self):
        weapon = {"name": "АК-74 «Резонанс»", "category": "weapons", "attack": 205, "rarity": "legendary"}

        self.assertEqual(calc_weapon_attack(weapon, 297, "legendary", 10), 1347)


if __name__ == "__main__":
    unittest.main()
