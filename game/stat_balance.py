"""Shared stat scaling helpers."""

from __future__ import annotations


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def diminishing_bonus(stat: int | float, *, baseline: int = 1, cap: float, scale: float) -> float:
    """
    Convert a stat into a soft-capped bonus.

    The curve is intentionally front-loaded: early stat points matter, while
    very high late-game values keep improving the character without reaching
    guaranteed outcomes.
    """
    value = max(0.0, float(stat or 0) - float(baseline))
    if value <= 0 or cap <= 0:
        return 0.0
    return float(cap) * value / (value + max(1.0, float(scale)))


def luck_crit_bonus(luck: int | float) -> int:
    return int(round(diminishing_bonus(luck, baseline=1, cap=28, scale=18)))


def luck_rare_find_bonus(luck: int | float) -> int:
    return int(round(diminishing_bonus(luck, baseline=1, cap=24, scale=22)))


def luck_artifact_bonus(luck: int | float) -> int:
    return int(round(diminishing_bonus(luck, baseline=1, cap=18, scale=26)))


def luck_outcome_bonus(luck: int | float) -> int:
    return int(round(diminishing_bonus(luck, baseline=1, cap=18, scale=24)))


def luck_initiative_bonus(luck: int | float) -> int:
    return int(round(diminishing_bonus(luck, baseline=1, cap=6, scale=20)))


def luck_bleed_chance_bonus(luck: int | float) -> int:
    return int(round(diminishing_bonus(luck, baseline=1, cap=25, scale=20)))


def luck_bleed_damage_bonus(luck: int | float) -> int:
    return int(round(diminishing_bonus(luck, baseline=1, cap=14, scale=18)))


def stamina_hp_bonus(stamina: int | float, *, per_point: int = 10) -> int:
    """
    HP from stamina.

    Values up to 20 keep the old linear feel. Late-game stamina keeps scaling,
    but cannot turn HP into an unbounded dump stat.
    """
    sta = max(1, int(stamina or 1))
    linear_cap = 20
    if sta <= linear_cap:
        return sta * per_point
    late_bonus = diminishing_bonus(sta, baseline=linear_cap, cap=760, scale=60)
    return linear_cap * per_point + int(round(late_bonus))


def stamina_energy_regen(stamina: int | float) -> int:
    """Combat energy restored per player turn from stamina."""
    return int(round(diminishing_bonus(stamina, baseline=4, cap=12, scale=50)))


def stamina_max_energy_bonus(stamina: int | float) -> int:
    """Maximum energy bonus from stamina."""
    return int(round(diminishing_bonus(stamina, baseline=4, cap=40, scale=80)))


def next_stamina_max_energy_breakpoint(stamina: int | float, *, max_stamina: int = 300) -> tuple[int, int] | None:
    """Return (stamina, max energy bonus) for the next visible max-energy increase."""
    current_stamina = max(1, int(stamina or 1))
    current_bonus = stamina_max_energy_bonus(current_stamina)
    for candidate in range(current_stamina + 1, max(1, int(max_stamina or 1)) + 1):
        bonus = stamina_max_energy_bonus(candidate)
        if bonus > current_bonus:
            return candidate, bonus
    return None


def next_stamina_energy_regen_breakpoint(stamina: int | float, *, max_stamina: int = 300) -> tuple[int, int] | None:
    """Return (stamina, regen) for the next visible combat energy regen increase."""
    current_stamina = max(1, int(stamina or 1))
    current_regen = stamina_energy_regen(current_stamina)
    for candidate in range(current_stamina + 1, max(1, int(max_stamina or 1)) + 1):
        regen = stamina_energy_regen(candidate)
        if regen > current_regen:
            return candidate, regen
    return None


def stamina_research_energy_discount(stamina: int | float) -> int:
    """Percent discount for research energy cost from stamina."""
    return int(round(diminishing_bonus(stamina, baseline=4, cap=20, scale=80)))


def rank_stat_cap(rank_tier: int | float | None) -> int:
    """
    Maximum base value for one player stat at the current rank.

    The old effective cap of 20 was too small for mid/late game, while having no
    cap lets a player dump every level point into one stat. This curve keeps
    early ranks familiar and opens enough room for real builds by level 167+.
    """
    tier = max(1, int(rank_tier or 1))
    return min(100, 20 + int(round((tier - 1) * 80 / 23)))
