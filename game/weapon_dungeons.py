"""Weapon upgrade material dungeons."""

from __future__ import annotations

import random
from dataclasses import dataclass

from game.weapon_progression import get_rank_ascension_limit
from infra import database

WAREHOUSE_17_ID = "склад_17"
DUNGEON_ENERGY_COST = 40
DUNGEON_WAVES = 3


@dataclass(frozen=True)
class DungeonThreat:
    id: str
    label: str
    min_rank_ascension: int
    enemy_level: int
    reward_mult: float
    description: str
    rewards: tuple[tuple[str, int, int, int], ...]


WAREHOUSE_17_THREATS: tuple[DungeonThreat, ...] = (
    DungeonThreat(
        id="i",
        label="Угроза I",
        min_rank_ascension=0,
        enemy_level=6,
        reward_mult=1.0,
        description="первые ящики снабжения, ранние пластины и малый оружейный опыт",
        rewards=(
            ("Оружейный конденсат", 3, 5, 100),
            ("Полевой оружейный журнал", 1, 1, 35),
            ("Резонансная пластина", 2, 4, 100),
        ),
    ),
    DungeonThreat(
        id="ii",
        label="Угроза II",
        min_rank_ascension=2,
        enemy_level=16,
        reward_mult=1.15,
        description="нижние коридоры склада, больше пластин и первые калибровочные наборы",
        rewards=(
            ("Оружейный конденсат", 4, 7, 100),
            ("Полевой оружейный журнал", 1, 2, 65),
            ("Резонансная пластина", 3, 5, 100),
            ("Армейский калибровочный набор", 1, 2, 55),
        ),
    ),
    DungeonThreat(
        id="iii",
        label="Угроза III",
        min_rank_ascension=4,
        enemy_level=30,
        reward_mult=1.35,
        description="техблок бункера, стабильный фарм калибровочных наборов",
        rewards=(
            ("Полевой оружейный журнал", 2, 3, 100),
            ("Армейский калибратор", 1, 1, 35),
            ("Резонансная пластина", 2, 4, 70),
            ("Армейский калибровочный набор", 2, 4, 100),
        ),
    ),
    DungeonThreat(
        id="iv",
        label="Угроза IV",
        min_rank_ascension=6,
        enemy_level=48,
        reward_mult=1.65,
        description="оружейная шахта под складом, закалённые стволы и крупный опыт",
        rewards=(
            ("Полевой оружейный журнал", 2, 4, 100),
            ("Армейский калибратор", 1, 2, 70),
            ("Армейский калибровочный набор", 2, 4, 70),
            ("Закалённый ствол", 2, 4, 100),
        ),
    ),
    DungeonThreat(
        id="v",
        label="Угроза V",
        min_rank_ascension=8,
        enemy_level=70,
        reward_mult=2.0,
        description="запечатанная камера резонанса, топовые ядра и материалы поздних прорывов",
        rewards=(
            ("Армейский калибратор", 2, 3, 100),
            ("Закалённый ствол", 3, 5, 100),
            ("Ядро оружейного резонанса", 1, 2, 80),
        ),
    ),
)

_THREATS_BY_ID = {threat.id: threat for threat in WAREHOUSE_17_THREATS}
_THREAT_ALIASES = {
    "1": "i",
    "i": "i",
    "I".lower(): "i",
    "угроза 1": "i",
    "угроза i": "i",
    "угроза i склад 17": "i",
    "2": "ii",
    "ii": "ii",
    "угроза 2": "ii",
    "угроза ii": "ii",
    "угроза ii склад 17": "ii",
    "3": "iii",
    "iii": "iii",
    "угроза 3": "iii",
    "угроза iii": "iii",
    "угроза iii склад 17": "iii",
    "4": "iv",
    "iv": "iv",
    "угроза 4": "iv",
    "угроза iv": "iv",
    "угроза iv склад 17": "iv",
    "5": "v",
    "v": "v",
    "угроза 5": "v",
    "угроза v": "v",
    "угроза v склад 17": "v",
}


def get_warehouse17_threat(threat_id: str | None) -> DungeonThreat | None:
    key = str(threat_id or "").strip().lower()
    key = _THREAT_ALIASES.get(key, key)
    return _THREATS_BY_ID.get(key)


def get_available_warehouse17_threats(rank_tier: int | None) -> tuple[DungeonThreat, ...]:
    ascension_limit = get_rank_ascension_limit(rank_tier)
    return tuple(
        threat for threat in WAREHOUSE_17_THREATS
        if ascension_limit >= threat.min_rank_ascension
    )


def is_warehouse17_threat_command(text: str | None) -> bool:
    return str(text or "").strip().lower() in _THREAT_ALIASES


def format_warehouse17_menu(player) -> str:
    rank_tier = player._get_rank_tier() if hasattr(player, "_get_rank_tier") else getattr(player, "rank_tier", 1)
    ascension_limit = get_rank_ascension_limit(rank_tier)
    lines = [
        "▰ ОРУЖЕЙНЫЙ БУНКЕР «СКЛАД 17»",
        "Коридоры под старой дорогой фонят оружейным резонансом. Внутри домен на 3 волны.",
        "",
        "• ВХОД",
        f"Энергия: {DUNGEON_ENERGY_COST}",
        "Волны: 3",
        f"Твой лимит прорыва по рангу: {ascension_limit}/10",
        "",
        "• УРОВНИ УГРОЗЫ",
    ]
    available_ids = {threat.id for threat in get_available_warehouse17_threats(rank_tier)}
    for threat in WAREHOUSE_17_THREATS:
        status = "доступно" if threat.id in available_ids else f"нужен прорыв ранга {threat.min_rank_ascension}/10"
        lines.append(f"{threat.label}: враги L{threat.enemy_level}, {status}")
        lines.append(f"  {threat.description}")
    lines.extend([
        "",
        "Выбери кнопку угрозы или напиши: угроза I.",
    ])
    return "\n".join(lines)


def _roll_rewards(threat: DungeonThreat) -> list[tuple[str, int]]:
    granted: list[tuple[str, int]] = []
    for item_name, min_qty, max_qty, chance in threat.rewards:
        if random.randint(1, 100) <= int(chance):
            qty = random.randint(int(min_qty), int(max_qty))
            granted.append((item_name, qty))
    if not granted:
        granted.append(("Оружейный конденсат", 3))
    return granted


def grant_warehouse17_rewards(vk_id: int, threat_id: str) -> list[tuple[str, int]]:
    threat = get_warehouse17_threat(threat_id) or WAREHOUSE_17_THREATS[0]
    granted = _roll_rewards(threat)
    for item_name, qty in granted:
        database.add_weapon_material(vk_id, item_name, qty)
    return granted


def start_warehouse17_run(player, vk, user_id: int, threat_text: str) -> dict:
    threat = get_warehouse17_threat(threat_text)
    if not threat:
        return {"success": False, "message": "Неизвестный уровень угрозы Склад-17."}

    rank_tier = player._get_rank_tier() if hasattr(player, "_get_rank_tier") else getattr(player, "rank_tier", 1)
    ascension_limit = get_rank_ascension_limit(rank_tier)
    if ascension_limit < threat.min_rank_ascension:
        return {
            "success": False,
            "message": (
                f"{threat.label} ещё закрыта рангом.\n"
                f"Нужно открыть прорыв ранга {threat.min_rank_ascension}/10, сейчас доступно {ascension_limit}/10."
            ),
        }

    energy = int(getattr(player, "energy", 0) or 0)
    if energy < DUNGEON_ENERGY_COST:
        return {
            "success": False,
            "message": f"Для входа в Склад 17 нужно {DUNGEON_ENERGY_COST} энергии. Сейчас: {energy}.",
        }

    player.energy = energy - DUNGEON_ENERGY_COST
    database.update_user_stats(user_id, energy=player.energy)

    dungeon_run = {
        "id": WAREHOUSE_17_ID,
        "name": "Оружейный бункер «Склад 17»",
        "threat_id": threat.id,
        "threat_label": threat.label,
        "wave": 1,
        "waves_total": DUNGEON_WAVES,
        "enemy_level": threat.enemy_level,
        "reward_mult": threat.reward_mult,
    }
    from handlers.combat import start_dungeon_combat

    started = start_dungeon_combat(player, vk, user_id, dungeon_run)
    if not started:
        player.energy = energy
        database.update_user_stats(user_id, energy=energy)
        return {"success": False, "message": "Не удалось запустить бой Склад-17."}

    return {"success": True, "message": f"{threat.label} запущена."}
