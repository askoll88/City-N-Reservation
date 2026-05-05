from __future__ import annotations

from infra import database
from models.player import (
    LEVEL_NOTICE_FROM_FLAG,
    LEVEL_NOTICE_PENDING_FLAG,
    LEVEL_NOTICE_TO_FLAG,
    UNSPENT_STAT_POINTS_FLAG,
    calculate_player_max_health,
)
from game.stat_balance import rank_stat_cap, stamina_max_energy_bonus

STAT_LABELS = {
    "strength": "Сила",
    "stamina": "Выносливость",
    "perception": "Восприятие",
    "luck": "Удача",
}

STAT_DESCRIPTIONS = {
    "strength": "урон и переносимый вес",
    "stamina": "макс. HP, максимум энергии и восстановление энергии",
    "perception": "поиск, аномалии и разведка",
    "luck": "криты, редкие находки и позитивные исходы событий",
}


def create_stat_choice_keyboard(*, inline: bool = True):
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor

    keyboard = VkKeyboard(one_time=False, inline=inline)
    keyboard.add_callback_button(
        "Сила",
        color=VkKeyboardColor.PRIMARY,
        payload={"command": "stat_choice", "stat": "strength"},
    )
    keyboard.add_callback_button(
        "Выносливость",
        color=VkKeyboardColor.PRIMARY,
        payload={"command": "stat_choice", "stat": "stamina"},
    )
    keyboard.add_line()
    keyboard.add_callback_button(
        "Восприятие",
        color=VkKeyboardColor.SECONDARY,
        payload={"command": "stat_choice", "stat": "perception"},
    )
    keyboard.add_callback_button(
        "Удача",
        color=VkKeyboardColor.SECONDARY,
        payload={"command": "stat_choice", "stat": "luck"},
    )
    return keyboard


def _is_level_notice_blocked(user_id: int) -> bool:
    from infra.state_manager import (
        has_pending_emission_risk_exit,
        has_pending_event,
        has_pending_loot_choice,
        has_pending_purchase,
        has_travel_state,
        is_in_anomaly,
        is_in_combat,
        is_researching,
    )

    return (
        is_in_combat(user_id)
        or is_researching(user_id)
        or has_travel_state(user_id)
        or is_in_anomaly(user_id)
        or has_pending_event(user_id)
        or has_pending_purchase(user_id)
        or has_pending_loot_choice(user_id)
        or has_pending_emission_risk_exit(user_id)
    )


def maybe_send_level_up_notification(vk, user_id: int) -> bool:
    """Отправить отложенное уведомление об уровне, если игрок не занят событием."""
    if _is_level_notice_blocked(user_id):
        return False

    pending = int(database.get_user_flag(user_id, LEVEL_NOTICE_PENDING_FLAG, 0) or 0)
    points = int(database.get_user_flag(user_id, UNSPENT_STAT_POINTS_FLAG, 0) or 0)
    if pending <= 0 or points <= 0:
        return False

    from_level = int(database.get_user_flag(user_id, LEVEL_NOTICE_FROM_FLAG, 0) or 0)
    to_level = int(database.get_user_flag(user_id, LEVEL_NOTICE_TO_FLAG, 0) or 0)
    level_line = f"{from_level} -> {to_level}" if from_level and to_level else "уровень повышен"

    vk.messages.send(
        user_id=user_id,
        message=(
            "НОВЫЙ УРОВЕНЬ\n\n"
            f"Прогресс: {level_line}\n"
            "Здоровье и энергия восстановлены.\n\n"
            f"Свободных очков характеристик: {points}\n"
            "Выбери, какую характеристику усилить."
        ),
        keyboard=create_stat_choice_keyboard().get_keyboard(),
        random_id=0,
    )
    database.set_user_flag(user_id, LEVEL_NOTICE_PENDING_FLAG, 0)
    database.set_user_flag(user_id, LEVEL_NOTICE_FROM_FLAG, 0)
    database.set_user_flag(user_id, LEVEL_NOTICE_TO_FLAG, 0)
    return True


def send_stat_choice_prompt(vk, user_id: int, prefix: str | None = None) -> bool:
    points = int(database.get_user_flag(user_id, UNSPENT_STAT_POINTS_FLAG, 0) or 0)
    if points <= 0:
        return False
    message = prefix + "\n\n" if prefix else ""
    message += (
        f"Свободных очков характеристик: {points}\n"
        "Выбери характеристику для прокачки."
    )
    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=create_stat_choice_keyboard().get_keyboard(),
        random_id=0,
    )
    return True


def apply_stat_choice(vk, user_id: int, stat: str) -> dict:
    stat = str(stat or "").strip().lower()
    if stat not in STAT_LABELS:
        return {"success": False, "message": "Характеристика устарела."}

    with database.db_cursor() as (cursor, _):
        cursor.execute(
            """
            SELECT id, level, rank_tier, health, energy, stamina, max_health_bonus,
                   strength, perception, luck, max_weight
            FROM users
            WHERE vk_id = %s
            FOR UPDATE
            """,
            (user_id,),
        )
        user = cursor.fetchone()
        if not user:
            return {"success": False, "message": "Персонаж не найден."}

        internal_id = int(user["id"])
        cursor.execute(
            """
            SELECT value FROM user_flags
            WHERE user_id = %s AND flag_name = %s
            FOR UPDATE
            """,
            (internal_id, UNSPENT_STAT_POINTS_FLAG),
        )
        points_row = cursor.fetchone()
        points = int(points_row["value"] if points_row else 0)
        if points <= 0:
            return {"success": False, "message": "Свободных очков нет."}

        old_value = int(user.get(stat, 1) or 1)
        stat_cap = rank_stat_cap(user.get("rank_tier", 1))
        if old_value >= stat_cap:
            return {
                "success": False,
                "message": (
                    f"{STAT_LABELS[stat]} уже упёрлась в лимит текущего ранга: {stat_cap}.\n"
                    "Подними ранг, чтобы открыть дальнейшую прокачку."
                ),
            }
        new_value = old_value + 1
        remaining = points - 1
        updates = {stat: new_value}

        if stat == "strength":
            updates["max_weight"] = int(user.get("max_weight", 10) or 10) + 2

        if stat == "stamina":
            level = int(user.get("level", 1) or 1)
            old_stamina = int(user.get("stamina", 1) or 1)
            bonus = int(user.get("max_health_bonus", 0) or 0)
            old_max_hp = calculate_player_max_health(level, old_stamina, bonus)
            new_max_hp = calculate_player_max_health(level, new_value, bonus)
            hp_delta = max(0, new_max_hp - old_max_hp)
            old_energy_bonus = stamina_max_energy_bonus(old_stamina)
            new_energy_bonus = stamina_max_energy_bonus(new_value)
            energy_delta = max(0, new_energy_bonus - old_energy_bonus)
            updates["health"] = min(new_max_hp, int(user.get("health", 0) or 0) + hp_delta)
            if energy_delta > 0:
                updates["energy"] = min(100 + new_energy_bonus, int(user.get("energy", 0) or 0) + energy_delta)

        sets = ", ".join(f"{key} = %s" for key in updates)
        params = list(updates.values()) + [user_id]
        cursor.execute(f"UPDATE users SET {sets} WHERE vk_id = %s", params)
        cursor.execute(
            """
            INSERT INTO user_flags (user_id, flag_name, value)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, flag_name) DO UPDATE
            SET value = EXCLUDED.value
            """,
            (internal_id, UNSPENT_STAT_POINTS_FLAG, remaining),
        )

    label = STAT_LABELS[stat]
    desc = STAT_DESCRIPTIONS[stat]
    msg = f"{label}: {old_value} -> {new_value}\nЭффект: {desc}."
    if stat == "strength":
        msg += "\nПереносимый вес: +2 кг."
    if stat == "stamina":
        msg += "\nМаксимальное HP выросло. Максимум энергии тоже растёт от выносливости."
    if remaining > 0:
        msg += f"\n\nОсталось очков: {remaining}"
    else:
        msg += "\n\nСвободные очки распределены."
    return {"success": True, "message": msg, "remaining": remaining}


def handle_stat_choice_callback(vk, user_id: int, stat: str):
    if _is_level_notice_blocked(user_id):
        return {"success": False, "message": "Сначала заверши текущее событие."}

    result = apply_stat_choice(vk, user_id, stat)
    try:
        from infra.state_manager import invalidate_player_cache
        invalidate_player_cache(user_id)
    except Exception:
        pass
    vk.messages.send(
        user_id=user_id,
        message=result["message"],
        keyboard=(create_stat_choice_keyboard().get_keyboard() if result.get("remaining", 0) > 0 else None),
        random_id=0,
    )
    return result
