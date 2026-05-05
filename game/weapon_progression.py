"""
Уровневый конвейер оружия.

Шаблон предмета задаёт базовый ATK, а конкретный экземпляр в инвентаре
получает уровень, ранг и стадию прорыва. Прокачка масштабирует ATK
процентно от базы, поэтому новое оружие падает L1, но не теряет свою основу.
"""
from __future__ import annotations

from game.gacha.event_items import get_event_weapon_max_attack_target, get_event_weapon_stat_profile
from models.enemies import get_weapon_type

WEAPON_RANKS = {
    "common": {"label": "обычное", "mult": 1.00, "price_mult": 1.00},
    "uncommon": {"label": "добротное", "mult": 1.12, "price_mult": 1.35},
    "rare": {"label": "редкое", "mult": 1.28, "price_mult": 1.85},
    "epic": {"label": "эпическое", "mult": 1.50, "price_mult": 2.65},
    "legendary": {"label": "легендарное", "mult": 1.85, "price_mult": 4.00},
}

TYPE_MULT = {
    "нож": 0.70,
    "пистолет": 0.85,
    "автомат": 1.00,
    "дробовик": 1.12,
    "пулемет": 1.05,
    "снайперка": 1.25,
}

DEFAULT_BASE_ATTACK_BY_TYPE = {
    "нож": 18,
    "пистолет": 24,
    "автомат": 44,
    "дробовик": 50,
    "пулемет": 56,
    "снайперка": 62,
}

EVENT_WEAPON_STAT_LABELS = {
    "crit_chance": "Крит. шанс",
    "crit_damage": "Крит. урон",
    "bleed_chance": "Шанс кровотечения",
    "bleed_damage": "Урон кровотечения",
}

MAX_WEAPON_LEVEL = 297
ASCENSION_CAPS = [10, 20, 40, 60, 90, 120, 150, 180, 210, 250, 297]

# 24 ранга игрока растягивают 10 прорывов оружия. Высокий ранг позволяет
# прокачать даже новое L1-оружие сразу до своего текущего доступного диапазона.
RANK_ASCENSION_LIMITS = [
    (1, 0),
    (2, 1),
    (4, 2),
    (6, 3),
    (8, 4),
    (10, 5),
    (12, 6),
    (14, 7),
    (16, 8),
    (19, 9),
    (24, 10),
]

WEAPON_XP_MATERIALS = {
    "Оружейный конденсат": 120,
    "Полевой оружейный журнал": 420,
    "Армейский калибратор": 1200,
}

ASCENSION_MATERIALS = {
    "Резонансная пластина",
    "Армейский калибровочный набор",
    "Закалённый ствол",
    "Ядро оружейного резонанса",
}
WEAPON_MATERIALS = frozenset({*WEAPON_XP_MATERIALS.keys(), *ASCENSION_MATERIALS})

ASCENSION_COSTS = {
    1: {"Резонансная пластина": 2},
    2: {"Резонансная пластина": 4},
    3: {"Резонансная пластина": 6, "Армейский калибровочный набор": 1},
    4: {"Армейский калибровочный набор": 3},
    5: {"Армейский калибровочный набор": 5, "Закалённый ствол": 1},
    6: {"Закалённый ствол": 3},
    7: {"Закалённый ствол": 5},
    8: {"Закалённый ствол": 7, "Ядро оружейного резонанса": 1},
    9: {"Ядро оружейного резонанса": 2},
    10: {"Ядро оружейного резонанса": 4},
}


def is_weapon(item: dict | None) -> bool:
    return bool(item and (item.get("category") or "").lower() in {"weapons", "rare_weapons"})


def normalize_weapon_rank(rank: str | None, item: dict | None = None) -> str:
    value = (rank or "").lower().strip()
    aliases = {
        "обычное": "common",
        "добротное": "uncommon",
        "редкое": "rare",
        "эпическое": "epic",
        "легендарное": "legendary",
        "unique": "epic",
    }
    value = aliases.get(value, value)
    if value in WEAPON_RANKS:
        return value

    rarity = ((item or {}).get("rarity") or "common").lower()
    category = ((item or {}).get("category") or "").lower()
    if rarity == "legendary":
        return "legendary"
    if rarity == "unique":
        return "epic"
    if rarity == "rare" or category == "rare_weapons":
        return "rare"
    return "common"


def weapon_rank_label(rank: str | None) -> str:
    return WEAPON_RANKS[normalize_weapon_rank(rank)].get("label", "обычное")


def get_weapon_required_level(item: dict | None) -> int:
    """Минимальный уровень владения шаблоном оружия."""
    if not is_weapon(item):
        return 1
    attack = int((item or {}).get("attack", 0) or 0)
    if attack <= 20:
        return 1
    if attack <= 32:
        return 5
    if attack <= 45:
        return 10
    if attack <= 60:
        return 20
    if attack <= 75:
        return 35
    if attack <= 90:
        return 50
    return 70


def clamp_weapon_level(level: int | None, player_level: int, item: dict | None = None) -> int:
    raw = int(level or 1)
    return max(1, min(MAX_WEAPON_LEVEL, raw))


def normalize_weapon_ascension(value: int | None) -> int:
    return max(0, min(10, int(value or 0)))


def get_weapon_cap(ascension: int | None) -> int:
    return ASCENSION_CAPS[normalize_weapon_ascension(ascension)]


def get_rank_ascension_limit(rank_tier: int | None) -> int:
    tier = max(1, int(rank_tier or 1))
    result = 0
    for required_tier, ascension in RANK_ASCENSION_LIMITS:
        if tier >= required_tier:
            result = ascension
    return result


def get_rank_weapon_level_cap(rank_tier: int | None) -> int:
    return get_weapon_cap(get_rank_ascension_limit(rank_tier))


def weapon_xp_to_next_level(level: int) -> int:
    lvl = max(1, min(MAX_WEAPON_LEVEL - 1, int(level or 1)))
    return int(80 + lvl * 22 + (lvl // 20) * 90)


def weapon_total_xp_for_level(level: int) -> int:
    lvl = max(1, min(MAX_WEAPON_LEVEL, int(level or 1)))
    return sum(weapon_xp_to_next_level(i) for i in range(1, lvl))


def weapon_level_from_total_xp(total_xp: int, cap: int) -> tuple[int, int]:
    cap = max(1, min(MAX_WEAPON_LEVEL, int(cap or 1)))
    remaining = max(0, int(total_xp or 0))
    level = 1
    while level < cap:
        need = weapon_xp_to_next_level(level)
        if remaining < need:
            break
        remaining -= need
        level += 1
    return level, remaining if level < cap else 0


def get_weapon_base_attack(item: dict | None) -> int:
    if not is_weapon(item):
        return int((item or {}).get("attack", 0) or 0)
    raw = int((item or {}).get("base_attack") or (item or {}).get("attack") or 0)
    if raw > 0:
        return raw
    weapon_type = get_weapon_type((item or {}).get("name"))
    return DEFAULT_BASE_ATTACK_BY_TYPE.get(weapon_type, 30)


def _weapon_progress_multiplier(weapon_level: int | None) -> float:
    """ATK растёт от каждого уровня оружия; прорыв только открывает следующий кап."""
    level = max(1, min(MAX_WEAPON_LEVEL, int(weapon_level or 1)))
    level_ratio = (level - 1) / max(1, MAX_WEAPON_LEVEL - 1)
    return 0.50 + level_ratio * 3.05


def calc_weapon_attack(
    item: dict | None,
    weapon_level: int | None,
    weapon_rank: str | None,
    weapon_ascension: int | None = 0,
) -> int:
    if not is_weapon(item):
        return int((item or {}).get("attack", 0) or 0)
    level = max(1, int(weapon_level or 1))
    rank = normalize_weapon_rank(weapon_rank, item)
    rank_mult = WEAPON_RANKS[rank]["mult"]
    base_attack = get_weapon_base_attack(item)
    attack = max(1, int(base_attack * _weapon_progress_multiplier(level) * rank_mult))
    target_max = get_event_weapon_max_attack_target((item or {}).get("name"))
    if (
        target_max
        and level >= MAX_WEAPON_LEVEL
        and normalize_weapon_ascension(weapon_ascension) >= 10
        and rank == "legendary"
    ):
        return target_max
    return attack


def _event_weapon_stat_ratio(weapon_level: int | None, weapon_ascension: int | None = 0) -> float:
    """Ивент-доп. стат растёт только после прорывов оружия."""
    ascension = normalize_weapon_ascension(weapon_ascension)
    return ascension / 10


def calc_event_weapon_bonus_stats(
    item: dict | None,
    weapon_level: int | None,
    weapon_ascension: int | None = 0,
) -> dict[str, int]:
    name = str((item or {}).get("name") or "").strip()
    profile = get_event_weapon_stat_profile(name)
    if not profile or not is_weapon(item):
        return {}
    ratio = _event_weapon_stat_ratio(weapon_level, weapon_ascension)
    result: dict[str, int] = {}
    for stat_name, bounds in (profile.get("stats") or {}).items():
        start, finish = bounds
        value = int(round(float(start) + (float(finish) - float(start)) * ratio))
        if value:
            result[str(stat_name)] = value
    return result


def get_event_weapon_bonus(
    item: dict | None,
    weapon_level: int | None,
    weapon_ascension: int | None = 0,
) -> dict | None:
    name = str((item or {}).get("name") or "").strip()
    profile = get_event_weapon_stat_profile(name)
    if not profile or not is_weapon(item):
        return None
    stats = calc_event_weapon_bonus_stats(item, weapon_level, weapon_ascension)
    if not stats:
        return None
    return {
        "name": profile["name"],
        "description": profile["description"],
        "stats": stats,
    }


def format_event_weapon_stats(stats: dict | None) -> str:
    parts = []
    for stat_name, value in (stats or {}).items():
        label = EVENT_WEAPON_STAT_LABELS.get(stat_name, stat_name)
        suffix = "" if stat_name == "bleed_damage" else "%"
        parts.append(f"{label} +{int(value)}{suffix}")
    return ", ".join(parts)


def roll_weapon_rank(player_level: int, item: dict | None = None) -> str:
    """Детерминированно простая таблица шансов ранга для нового экземпляра."""
    import random

    if not is_weapon(item):
        return normalize_weapon_rank(None, item)

    lvl = max(1, int(player_level or 1))
    rarity_floor = normalize_weapon_rank(None, item)
    roll = random.randint(1, 100)

    if lvl >= 50 and roll >= 98:
        rolled = "legendary"
    elif lvl >= 30 and roll >= 93:
        rolled = "epic"
    elif lvl >= 12 and roll >= 82:
        rolled = "rare"
    elif roll >= 62:
        rolled = "uncommon"
    else:
        rolled = "common"

    order = ["common", "uncommon", "rare", "epic", "legendary"]
    return order[max(order.index(rolled), order.index(rarity_floor))]


def roll_shop_weapon_level(
    player_level: int,
    item: dict | None = None,
    spread: int = 2,
    seed_key: str | None = None,
) -> int:
    """
    Уровень оружия на витрине NPC: небольшой разброс вокруг уровня игрока.
    По seed_key уровень стабилен в рамках одной ротации/пользователя.
    """
    import random

    if not is_weapon(item):
        return 1

    lvl = max(1, int(player_level or 1))
    spread = max(0, int(spread or 0))
    required = get_weapon_required_level(item)

    min_level = max(required, lvl - spread)
    max_level = max(min_level, lvl + spread)

    rng = random.Random(str(seed_key)) if seed_key is not None else random
    return int(rng.randint(min_level, max_level))


def weapon_upgrade_cost(item: dict | None, current_level: int, target_level: int, rank: str | None) -> int:
    current_level = max(1, int(current_level or 1))
    target_level = max(current_level, int(target_level or current_level))
    delta = target_level - current_level
    if delta <= 0:
        return 0
    rank_mult = WEAPON_RANKS[normalize_weapon_rank(rank, item)]["price_mult"]
    required = get_weapon_required_level(item)
    base = 65 + required * 4
    return max(1, int(delta * base * rank_mult))
