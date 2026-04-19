"""
Уровневый конвейер оружия.

Шаблон предмета задаёт тип оружия, а конкретный экземпляр в инвентаре
получает уровень и ранг. Урон считается от уровня + ранга, а не от старого
плоского attack из справочника.
"""
from __future__ import annotations

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
    player_level = max(1, int(player_level or 1))
    required = get_weapon_required_level(item)
    raw = int(level or min(player_level, required))
    return max(1, min(player_level, raw))


def calc_weapon_attack(item: dict | None, weapon_level: int | None, weapon_rank: str | None) -> int:
    if not is_weapon(item):
        return int((item or {}).get("attack", 0) or 0)
    level = max(1, int(weapon_level or get_weapon_required_level(item)))
    rank = normalize_weapon_rank(weapon_rank, item)
    weapon_type = get_weapon_type((item or {}).get("name"))
    type_mult = TYPE_MULT.get(weapon_type, 1.0)
    rank_mult = WEAPON_RANKS[rank]["mult"]
    base = 10 + level * 3.2
    return max(1, int(base * type_mult * rank_mult))


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
