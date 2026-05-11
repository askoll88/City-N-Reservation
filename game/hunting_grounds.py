"""
AFK-охота в лесных угодьях.

Это отдельная активность, не обычное исследование: игрок выбирает тактику,
ждёт таймер и получает результат по следу, риску и характеристикам.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

from infra import database
from models.player import invalidate_player_cache


HUNTING_GROUNDS_LOCATION = "охотничьи_угодья"
HUNTING_UNLOCK_FLAG = "forest_hunting_grounds_unlocked"
HUNTING_STATE_KEY = "hunting_grounds_state"
HUNT_DURATION_SECONDS = 5 * 60


@dataclass(frozen=True)
class HuntingTactic:
    id: str
    label: str
    energy_cost: int
    risk: int
    score_bonus: int
    rare_bonus: int
    description: str


TACTICS: dict[str, HuntingTactic] = {
    "quiet": HuntingTactic(
        id="quiet",
        label="Тихая тропа",
        energy_cost=8,
        risk=6,
        score_bonus=-4,
        rare_bonus=-5,
        description="меньше риска, чаще мелкая добыча или пустой след",
    ),
    "ambush": HuntingTactic(
        id="ambush",
        label="Засада у солонца",
        energy_cost=12,
        risk=12,
        score_bonus=4,
        rare_bonus=3,
        description="сбалансированная охота с нормальным шансом трофея",
    ),
    "deep": HuntingTactic(
        id="deep",
        label="Глубокий след",
        energy_cost=18,
        risk=22,
        score_bonus=12,
        rare_bonus=10,
        description="выше шанс редкой добычи, но больше шанс нарваться на зверя",
    ),
}


ANIMALS = {
    "empty": [
        ("Пустой след", [], 25, 0),
        ("Сбитая тропа", [], 35, 0),
    ],
    "common": [
        ("Рыжая лиса", [("Лисий хвост", 1)], 70, 2),
        ("Дикая собака", [("Ломоть мяса", 1)], 60, 2),
        ("Подраненный кабан", [("Ломоть мяса", 1), ("Шкура кабана", 1)], 80, 3),
    ],
    "uncommon": [
        ("Серый волк", [("Шкура волка", 1), ("Ломоть мяса", 1)], 120, 4),
        ("Крупный кабан-секач", [("Шкура кабана", 1), ("Ломоть мяса", 2)], 140, 5),
        ("Лесной снорк", [("Кость снорка", 1)], 130, 5),
    ],
    "rare": [
        ("Старый медведь", [("Медвежий жир", 1), ("Медвежья шкура", 1)], 220, 7),
        ("Белая лиса", [("Лисий хвост", 2), ("Чистая звериная кость", 1)], 210, 7),
        ("Кровосос на лежке", [("Коготь кровососа", 1), ("Мутная железа", 1)], 240, 8),
    ],
    "mutant": [
        ("Клыкастая тень", [("Клык мутанта", 1), ("Мутная железа", 1)], 280, 10),
        ("Пятнистый медведь-мутант", [("Медвежий жир", 1), ("Клык мутанта", 1)], 320, 11),
    ],
}


TACTIC_ALIASES = {
    "тихая тропа": "quiet",
    "тихо": "quiet",
    "тихая": "quiet",
    "засада у солонца": "ambush",
    "засада": "ambush",
    "солонец": "ambush",
    "глубокий след": "deep",
    "глубоко": "deep",
    "след": "deep",
}


def _now() -> int:
    return int(time.time())


def _get_state(vk_id: int) -> dict | None:
    state = database.get_runtime_state(vk_id, HUNTING_STATE_KEY)
    return state if isinstance(state, dict) and state else None


def _set_state(vk_id: int, state: dict):
    database.set_runtime_state(vk_id, HUNTING_STATE_KEY, state)


def _clear_state(vk_id: int):
    database.clear_runtime_state(vk_id, HUNTING_STATE_KEY)


def _has_unlock(vk_id: int) -> bool:
    return (
        int(database.get_user_flag(vk_id, HUNTING_UNLOCK_FLAG, 0) or 0) > 0
        or int(database.get_user_flag(vk_id, "forest_hunting_unlocked", 0) or 0) > 0
    )


def _stat(player, name: str) -> int:
    return max(0, int(getattr(player, name, 0) or 0))


def _pick_tier(player, tactic: HuntingTactic, seed: int) -> tuple[str, bool]:
    rng = random.Random(seed)
    perception = _stat(player, "perception")
    luck = _stat(player, "luck")
    level = _stat(player, "level")
    score = rng.randint(1, 100)
    score += min(22, perception * 2)
    score += min(16, luck * 2)
    score += min(10, level // 3)
    score += tactic.score_bonus

    risk_chance = max(3, tactic.risk - perception // 2 - luck // 4)
    ambushed = rng.randint(1, 100) <= risk_chance
    if ambushed:
        score -= rng.randint(10, 22)

    rare_shift = tactic.rare_bonus
    if score < 36:
        return "empty", ambushed
    if score < 66:
        return "common", ambushed
    if score < 86:
        return "uncommon", ambushed
    if score < 98 - rare_shift:
        return "rare", ambushed
    return "mutant", ambushed


def _format_menu(player, active: bool = False) -> str:
    lines = [
        "🐾 ОХОТНИЧЬИ УГОДЬЯ",
        "",
        "Выбери тактику. Охота займёт около 5 минут и не заменяет обычное исследование.",
        "",
    ]
    for tactic in TACTICS.values():
        lines.append(f"• {tactic.label}: {tactic.energy_cost}⚡, {tactic.description}.")
    lines.extend([
        "",
        f"Твои факторы: восприятие {_stat(player, 'perception')}, удача {_stat(player, 'luck')}.",
    ])
    if active:
        lines.append("Сейчас у тебя уже идёт охота.")
    return "\n".join(lines)


def show_hunting_menu(player, vk, user_id: int):
    from handlers.keyboards import create_hunting_grounds_keyboard

    active = _get_state(user_id) is not None
    vk.messages.send(
        user_id=user_id,
        message=_format_menu(player, active=active),
        keyboard=create_hunting_grounds_keyboard(active=active).get_keyboard(),
        random_id=0,
    )


def start_hunt(player, vk, user_id: int, tactic_id: str):
    from handlers.keyboards import create_hunting_grounds_keyboard, create_location_keyboard

    if player.current_location_id != HUNTING_GROUNDS_LOCATION:
        return False
    if not _has_unlock(user_id):
        vk.messages.send(
            user_id=user_id,
            message="🌲 Лесник ещё не дал тебе метки к угодьям. Вернись в заимку и пройди его проверку.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return True
    if _get_state(user_id):
        return check_hunt(player, vk, user_id)

    tactic = TACTICS[tactic_id]
    energy = int(getattr(player, "energy", 0) or 0)
    if energy < tactic.energy_cost:
        vk.messages.send(
            user_id=user_id,
            message=f"⚡ Не хватает энергии для охоты. Нужно {tactic.energy_cost}, у тебя {energy}.",
            keyboard=create_hunting_grounds_keyboard(active=False).get_keyboard(),
            random_id=0,
        )
        return True

    player.energy = energy - tactic.energy_cost
    database.update_user_stats(user_id, energy=player.energy)
    state = {
        "started_at": _now(),
        "duration": HUNT_DURATION_SECONDS,
        "tactic": tactic.id,
        "seed": random.randint(1, 2_000_000_000),
    }
    _set_state(user_id, state)
    vk.messages.send(
        user_id=user_id,
        message=(
            f"🐾 Ты начал охоту: {tactic.label}.\n\n"
            f"Потрачено: {tactic.energy_cost}⚡.\n"
            "Лесник учил: на охоте важна не скорость, а момент. Вернись через несколько минут и проверь след."
        ),
        keyboard=create_hunting_grounds_keyboard(active=True).get_keyboard(),
        random_id=0,
    )
    return True


def check_hunt(player, vk, user_id: int):
    from handlers.keyboards import create_hunting_grounds_keyboard

    state = _get_state(user_id)
    if not state:
        show_hunting_menu(player, vk, user_id)
        return True

    now = _now()
    started = int(state.get("started_at", now) or now)
    duration = max(30, int(state.get("duration", HUNT_DURATION_SECONDS) or HUNT_DURATION_SECONDS))
    remaining = started + duration - now
    if remaining > 0:
        vk.messages.send(
            user_id=user_id,
            message=f"🐾 След ещё не закрылся.\nОсталось примерно: {max(1, remaining // 60)} мин. {remaining % 60} сек.",
            keyboard=create_hunting_grounds_keyboard(active=True).get_keyboard(),
            random_id=0,
        )
        return True

    tactic = TACTICS.get(str(state.get("tactic") or "ambush"), TACTICS["ambush"])
    tier, ambushed = _pick_tier(player, tactic, int(state.get("seed") or random.randint(1, 999999)))
    rng = random.Random(int(state.get("seed") or 1) + 17)
    animal_name, rewards, xp_gain, trail_value = rng.choice(ANIMALS[tier])

    reward_lines = []
    for item_name, qty in rewards:
        if database.add_item_to_inventory(user_id, item_name, qty):
            reward_lines.append(f"• {item_name} x{qty}")

    damage_line = ""
    if ambushed:
        hp_loss = rng.randint(8, 22) + (6 if tactic.id == "deep" else 0)
        energy_loss = rng.randint(3, 9)
        player.health = max(1, int(getattr(player, "health", 1) or 1) - hp_loss)
        player.energy = max(0, int(getattr(player, "energy", 0) or 0) - energy_loss)
        database.update_user_stats(user_id, health=player.health, energy=player.energy)
        damage_line = f"\n\n⚠️ Добыча дала отпор: -{hp_loss} HP, -{energy_loss}⚡."

    gained_xp = 0
    if xp_gain > 0:
        gained_xp = int(player.add_experience(xp_gain))

    if trail_value > 0:
        database.set_user_flag(user_id, "forest_hunting_trail_score", int(database.get_user_flag(user_id, "forest_hunting_trail_score", 0) or 0) + trail_value)

    _clear_state(user_id)
    invalidate_player_cache(user_id)

    if not reward_lines:
        result_text = (
            f"🐾 Охота завершена: {animal_name}.\n\n"
            "След ушёл в мокрый валежник. Ты нашёл место лёжки, но добычу брать было уже поздно."
        )
    else:
        result_text = (
            f"🐾 Охота завершена: {animal_name}.\n\n"
            "Добыча:\n"
            + "\n".join(reward_lines)
        )
    if gained_xp:
        result_text += f"\n\nОпыт: +{gained_xp}."
    result_text += damage_line

    vk.messages.send(
        user_id=user_id,
        message=result_text,
        keyboard=create_hunting_grounds_keyboard(active=False).get_keyboard(),
        random_id=0,
    )
    return True


def cancel_hunt(player, vk, user_id: int):
    from handlers.keyboards import create_hunting_grounds_keyboard

    if _get_state(user_id):
        _clear_state(user_id)
        message = "🐾 Ты свернул охоту и вернулся к меткам. Потраченную энергию уже не вернуть."
    else:
        message = "🐾 Сейчас у тебя нет активной охоты."
    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=create_hunting_grounds_keyboard(active=False).get_keyboard(),
        random_id=0,
    )
    return True


def handle_hunting_command(player, vk, user_id: int, text: str) -> bool:
    normalized = (text or "").strip().lower()
    if normalized in {"охотиться", "охота", "угодья"}:
        show_hunting_menu(player, vk, user_id)
        return True
    if normalized in {"проверить охоту", "проверить", "след", "идти"}:
        return check_hunt(player, vk, user_id)
    if normalized in {"отменить охоту", "отмена охоты", "отмена", "стоп"}:
        return cancel_hunt(player, vk, user_id)
    tactic_id = TACTIC_ALIASES.get(normalized)
    if tactic_id:
        return start_hunt(player, vk, user_id, tactic_id)
    return False
