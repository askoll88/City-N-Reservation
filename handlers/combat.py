"""
Обработчики боя и исследования
"""
from __future__ import annotations

import random
import time
import threading
from infra import config
from infra import database
from models import enemies
from game import ui
from game.constants import RESEARCH_LOCATIONS
from infra.state_manager import _combat_state, set_combat_state, is_in_combat, get_combat_data, clear_research_state
_research_timers = {}  # {user_id: {"start_time": timestamp, "time_sec": int, "player_data": {...}}}
_skill_cooldowns = {}  # {user_id: {"skill_name": turns_remaining}}
_active_skill_effects = {}  # {user_id: {"effect_name": turns_remaining, ...}}

# Гарантированная аномалия: не реже 1 раза в N исследований.
ANOMALY_GUARANTEE_RESEARCHES = 150
ANOMALY_GUARANTEE_FLAG = "research_no_anomaly_streak"

# Без детектора можно "влететь" в аномалию и потерять ресурсы.
ANOMALY_BLIND_MISSTEP_CHANCE = 10
ANOMALY_BLIND_ITEM_LOSS_CHANCE = 45
SAWDUST_SOUP_RESEARCH_DROP_CHANCE = 2  # 2% среди событий "предмет": очень редкий странный лут


# === События исследования ===
RESEARCH_EVENTS = {
    # Ничего не найдено (уменьшили шанс)
    "nothing": {
        "chance": 14,
        "message": "Ты обыскал территорию...\n\nНичего не найдено.",
        "danger": 0
    },
    # Предметы (увеличили шансы)
    "common_item": {
        "chance": 22,
        "message": "Что-то найдено!",
        "danger": 0,
        "type": "item",
        "rarity": "common"
    },
    "rare_item": {
        "chance": 12,
        "message": "Ценная находка!",
        "danger": 0,
        "type": "item",
        "rarity": "rare"
    },
    "artifact": {
        "chance": 10,
        "message": "Найден артефакт!",
        "danger": 0,
        "type": "artifact"
    },
    # Враги (максимальные шансы)
    "mutant": {
        "chance": 38,
        "message": "АТАКА МУТАНТА!",
        "danger": 22,
        "type": "enemy",
        "enemy_type": "mutant"
    },
    "bandit": {
        "chance": 30,
        "message": "Обнаружен бандит!",
        "danger": 18,
        "type": "enemy",
        "enemy_type": "bandit"
    },
    "military": {
        "chance": 20,
        "message": "Военный патруль!",
        "danger": 26,
        "type": "enemy",
        "enemy_type": "military"
    },
    # Опасность (максимальные шансы)
    "anomaly": {
        "chance": 16,
        "message": "Попадание в аномалию!",
        "danger": 24,
        "type": "anomaly"
    },
    "radiation": {
        "chance": 14,
        "message": "Радиоактивная зона!",
        "danger": 16,
        "type": "radiation"
    },
    "trap": {
        "chance": 14,
        "message": "Попадание в ловушку!",
        "danger": 18,
        "type": "trap"
    },
    # Бонусы (увеличили)
    "stash": {
        "chance": 9,
        "message": "Найден тайник сталкера!",
        "danger": 0,
        "type": "stash"
    },
    "survivor": {
        "chance": 8,
        "message": "Встречен выживший сталкер",
        "danger": 0,
        "type": "survivor"
    },
    "military_cache": {
        "chance": 8,
        "message": "Найден военный ящик с гильзами!",
        "danger": 0,
        "type": "shell_cache"
    },
    "field_lab_data": {
        "chance": 7,
        "message": "Найдены ценные лабораторные данные!",
        "danger": 0,
        "type": "intel"
    },
    "abandoned_camp": {
        "chance": 9,
        "message": "Обнаружен брошенный лагерь сталкеров.",
        "danger": 0,
        "type": "camp"
    },
    "artifact_cluster": {
        "chance": 6,
        "message": "Ты наткнулся на скопление артефактов!",
        "danger": 0,
        "type": "artifact_cluster"
    },
    "psi_echo": {
        "chance": 10,
        "message": "Пси-эхо накрывает сознание!",
        "danger": 16,
        "type": "psi"
    },
    "blood_trail": {
        "chance": 11,
        "message": "Свежий кровавый след уходит в чащу...",
        "danger": 20,
        "type": "trail"
    }
}

# Время исследования (сек) -> множитель шансов
RESEARCH_TIME_MULTIPLIERS = {
    5: {"chance": 0.9, "danger": 0.75, "name": "Быстрый поиск"},
    10: {"chance": 1.2, "danger": 1.0, "name": "Обычный поиск"},
    15: {"chance": 1.45, "danger": 1.2, "name": "Тщательный поиск"}
}

# Энергия затрачиваемая на исследование
RESEARCH_ENERGY_COST = {
    5: 1,
    10: 2,
    15: 3
}

# Базовые уровни зон для мягкого скейлинга врагов
ZONE_LEVELS = {
    "дорога_военная_часть": 8,
    "дорога_нии": 12,
    "дорога_зараженный_лес": 16,
}

# Роли врагов: делают поведение боев менее однообразным
ENEMY_ROLE_PROFILES = {
    "bruiser": {
        "label": "Танк",
        "hp_mult": 1.25,
        "dmg_mult": 0.90,
        "speed_mod": -2,
    },
    "assassin": {
        "label": "Хищник",
        "hp_mult": 0.90,
        "dmg_mult": 1.15,
        "speed_mod": 2,
        "evade_chance": 18,  # шанс уклонения от атаки игрока
    },
    "controller": {
        "label": "Контролёр",
        "hp_mult": 1.00,
        "dmg_mult": 1.05,
        "speed_mod": 1,
        "drain_chance": 35,  # шанс высосать энергию при попадании
        "drain_min": 6,
        "drain_max": 12,
    },
}

# Ранняя игра: дорогое оружие не должно превращать персонажа 1-15 уровня
# в убийцу всей зоны, пока игрок ещё не умеет с ним работать.
EARLY_WEAPON_MASTERY_CAP_LEVEL = 15
EARLY_WEAPON_MASTERY_CAP_BASE = 26
EARLY_WEAPON_MASTERY_CAP_PER_LEVEL = 5


def _get_main_imports():
    """Ленивый импорт для избежания циклической зависимости"""
    import main
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
    return _combat_state, main.create_location_keyboard, VkKeyboard, VkKeyboardColor


def _clamp(value: int, min_val: int, max_val: int) -> int:
    return max(min_val, min(max_val, value))


def _apply_early_weapon_mastery_cap(player, damage: int, weapon_is_knife: bool = False) -> tuple[int, int]:
    """Ограничить урон дорогого оружия на ранних уровнях, не трогая ножи и кулаки."""
    lvl = max(1, int(getattr(player, "level", 1) or 1))
    if weapon_is_knife or lvl > EARLY_WEAPON_MASTERY_CAP_LEVEL:
        return int(damage), 0

    cap = EARLY_WEAPON_MASTERY_CAP_BASE + lvl * EARLY_WEAPON_MASTERY_CAP_PER_LEVEL
    damage = int(damage)
    if damage <= cap:
        return damage, 0
    return cap, cap


def _calculate_incoming_damage(player, enemy_damage: int, total_defense: int) -> tuple[int, int]:
    """Посчитать входящий урон с мягкой защитой от резких просадок в ранней игре."""
    final_damage = max(1, int(enemy_damage) - int(total_defense))
    lvl = max(1, int(getattr(player, "level", 1) or 1))
    if lvl <= 10:
        max_health = max(1, int(getattr(player, "max_health", 100) or 100))
        per_hit_cap = max(8, int(max_health * (0.18 + lvl * 0.01)))
        if final_damage > per_hit_cap:
            return per_hit_cap, per_hit_cap
    return final_damage, 0


def _get_player_rank_tier(player) -> int:
    """Безопасно получить текущий ранг (тир) игрока."""
    try:
        getter = getattr(player, "_get_rank_tier", None)
        if callable(getter):
            return max(1, int(getter() or 1))
    except Exception:
        pass
    return 1


def _scale_xp_reward(base_xp: int, player, source: str = "combat", enemy_level: int | None = None) -> int:
    """
    Скейл XP по прогрессии игрока.
    Цель: не "душить" раннюю игру и не обрушивать темп в мид/эндгейме.
    """
    base = max(1, int(base_xp or 1))
    lvl = max(1, int(getattr(player, "level", 1) or 1))
    rank_tier = _get_player_rank_tier(player)

    # Базовый рост за уровень и ранг.
    level_mult = 1.0 + min(2.2, max(0, lvl - 1) / 140.0)
    rank_mult = 1.0 + min(0.9, max(0, rank_tier - 1) * 0.04)

    # Дополнительный контекстный коэффициент.
    context_mult = 1.0
    if source == "combat":
        e_lvl = max(1, int(enemy_level or lvl))
        context_mult = 0.9 + min(2.4, e_lvl / 120.0)
    elif source == "research":
        context_mult = 1.0 + min(0.8, lvl / 250.0)

    xp = int(base * level_mult * rank_mult * context_mult)
    return max(base, xp)


def _format_mult_delta(mult: float) -> str:
    """Форматирование множителя в вид +N% / -N%."""
    delta_pct = int(round((float(mult) - 1.0) * 100))
    if delta_pct > 0:
        return f"+{delta_pct}%"
    if delta_pct < 0:
        return f"{delta_pct}%"
    return "0%"


def _build_research_modifiers_info(location_id: str, time_sec: int) -> tuple[str, str]:
    """Собрать инфо по модификаторам локации/событий для сообщения старта исследования."""
    from game.location_mechanics import (
        get_location_modifier,
        get_zone_mutation_state,
        get_energy_cost_mult,
        get_find_chance_mult,
        get_danger_mult,
        get_radiation_mult,
    )
    from game.emission import is_emission_aftermath_active, get_emission_artifact_bonus
    from game.limited_events import get_active_limited_event, get_limited_event_modifiers

    mod = get_location_modifier(location_id) or {}
    loc_name = mod.get("name", location_id)

    # Базовые моды локации (без временных ивентов)
    energy_mult = float(mod.get("energy_cost_mult", 1.0))
    base_find_mult = float(mod.get("find_chance_mult", 1.0))
    base_danger_mult = float(mod.get("danger_mult", 1.0))
    radiation_mult = float(mod.get("radiation_mult", 1.0))

    # Итоговые моды (с учётом ивентов, например мутации)
    find_mult = get_find_chance_mult(location_id)
    danger_mult = get_danger_mult(location_id)

    mode = RESEARCH_TIME_MULTIPLIERS.get(time_sec, {"chance": 1.0, "danger": 1.0})
    mode_find_mult = float(mode.get("chance", 1.0))
    mode_danger_mult = float(mode.get("danger", 1.0))

    lines = [
        f"• Локация: ⚡ {_format_mult_delta(energy_mult)} к расходу энергии",
        f"• Локация: 🔍 {_format_mult_delta(base_find_mult)} к шансу находок",
        f"• Локация: ⚠️ {_format_mult_delta(base_danger_mult)} к опасным событиям",
        f"• Локация: ☢️ {_format_mult_delta(radiation_mult)} к радиации",
        f"• Режим поиска: 🔍 {_format_mult_delta(mode_find_mult)} к находкам",
        f"• Режим поиска: ⚠️ {_format_mult_delta(mode_danger_mult)} к риску",
    ]

    mutation = get_zone_mutation_state(location_id)
    if mutation.get("active"):
        lines.append(
            f"• Ивент Зоны: 🌀 активна мутация (+{int(mutation.get('bonus_find', 0) * 100)}% находки, "
            f"+{int(mutation.get('bonus_danger', 0) * 100)}% опасность)"
        )
        lines.append(f"• Итого по зоне: 🔍 {_format_mult_delta(find_mult)} | ⚠️ {_format_mult_delta(danger_mult)}")

    unique = mod.get("unique_mechanic")
    if unique == "ambush":
        lines.append(f"• Ивент Зоны: 💀 шанс засады {int(float(mod.get('ambush_chance', 0)) * 100)}%")
    elif unique == "zone_mutation":
        lines.append(f"• Ивент Зоны: 🌀 шанс мутации {int(float(mod.get('zone_mutation_chance', 0)) * 100)}%")
    elif unique == "mutant_hunt":
        lines.append(
            f"• Ивент Зоны: 🐺 шанс охоты мутантов {int(float(mod.get('mutant_hunt_chance', 0)) * 100)}%"
        )

    if is_emission_aftermath_active():
        artifact_mult = get_emission_artifact_bonus()
        artifact_bonus = int(round((artifact_mult - 1.0) * 100))
        rare_enemy_bonus = int(round(float(config.EMISSION_BONUS_RARE_ENEMY_CHANCE) * 100))
        lines.append(f"• После выброса: 💎 +{artifact_bonus}% к шансу артефакта")
        lines.append(f"• После выброса: ☣️ шанс редкого врага {rare_enemy_bonus}%")

    limited = get_active_limited_event()
    if limited:
        mods = get_limited_event_modifiers()
        find_bonus = int(round((mods.get("research_find_mult", 1.0) - 1.0) * 100))
        danger_bonus = int(round((mods.get("research_danger_mult", 1.0) - 1.0) * 100))
        art_bonus = int(round((mods.get("artifact_event_mult", 1.0) - 1.0) * 100))
        enemy_bonus = int(round((mods.get("enemy_event_mult", 1.0) - 1.0) * 100))
        mins_left = max(0, int(limited.get("seconds_left", 0)) // 60)
        lines.append(f"• Глобальный ивент: {limited.get('name')} (ещё ~{mins_left} мин)")
        lines.append(
            f"• Глобальный ивент: 🔍 {find_bonus:+d}% | ⚠️ {danger_bonus:+d}% | "
            f"💎 {art_bonus:+d}% | 👾 {enemy_bonus:+d}%"
        )

    return loc_name, "\n".join(lines)


def _get_zone_level(location_id: str) -> int:
    return ZONE_LEVELS.get(location_id, 10)


def _filter_enemies_by_type(enemy_list: list[dict], enemy_type: str) -> list[dict]:
    """Отфильтровать список врагов по типу."""
    if not enemy_type:
        return list(enemy_list)

    et = enemy_type.lower().strip()
    if et == "mutant":
        return [
            e for e in enemy_list
            if any(k in e.get("name", "").lower() for k in ("мутант", "химера", "волк", "аномал", "зомби", "биолог"))
        ]
    if et == "bandit":
        return [e for e in enemy_list if "бандит" in e.get("name", "").lower()]
    if et == "military":
        return [e for e in enemy_list if "военн" in e.get("name", "").lower() or "солдат" in e.get("name", "").lower()]
    return list(enemy_list)


def _get_enemy_by_type_for_location(location_id: str, enemy_type: str):
    """Взять врага нужного типа в рамках текущей локации (без перескока в чужие биомы)."""
    loc_enemies = list(enemies.ENEMIES.get(location_id, []))
    if not loc_enemies:
        return None

    filtered = _filter_enemies_by_type(loc_enemies, enemy_type)
    if not filtered:
        return None
    return random.choice(filtered)


def _scale_enemy_for_player(player, base_enemy: dict, location_id: str, allow_elite: bool = True) -> dict:
    """Собрать боевой профиль врага со стабильным скейлингом по уровню игрока."""
    player_level = max(1, int(getattr(player, "level", 1) or 1))
    rank_tier = _get_player_rank_tier(player)
    zone_level = _get_zone_level(location_id)

    # Раньше уровень был зажат до zone+4, из-за чего на хай-левеле враги "застревали" около 20.
    # Новый подход: смесь уровня зоны и игрока + шум, с мягкими ограничениями.
    rank_level_bonus = int(max(0, rank_tier - 1) * 0.45)
    desired_level = int(round(zone_level * 0.35 + player_level * 0.75)) + rank_level_bonus
    spread = 1 + min(4, player_level // 20)  # 1..5
    enemy_level = desired_level + random.randint(-spread, spread)
    min_enemy_level = max(1, int(player_level * 0.55) - 2)
    max_enemy_level = max(zone_level + 6, int(player_level * 1.15) + 4)
    enemy_level = _clamp(enemy_level, min_enemy_level, max_enemy_level)

    # Плавный рост статов без резких скачков.
    hp_mult = 1.0 + 0.035 * max(0, enemy_level - 1)
    dmg_mult = 1.0 + 0.028 * max(0, enemy_level - 1)
    hp_mult *= 1.0 + min(0.55, max(0, rank_tier - 1) * 0.025)
    dmg_mult *= 1.0 + min(0.40, max(0, rank_tier - 1) * 0.018)

    role_key = random.choices(
        population=list(ENEMY_ROLE_PROFILES.keys()),
        weights=[35, 35, 30],
        k=1,
    )[0]
    role = ENEMY_ROLE_PROFILES[role_key]
    hp_mult *= role.get("hp_mult", 1.0)
    dmg_mult *= role.get("dmg_mult", 1.0)

    # Элитные версии дают всплеск сложности и награды.
    # allow_elite=False используется для режимов, где элитки нужно ограничить (например travel).
    elite_chance = 0.0 if player_level < 12 else min(0.18, 0.02 + (player_level - 10) * 0.0025)
    is_elite = allow_elite and enemy_level >= zone_level and random.random() < elite_chance
    if is_elite:
        hp_mult *= 1.20
        dmg_mult *= 1.15

    scaled_hp = max(20, int(base_enemy["hp"] * hp_mult))
    scaled_dmg = max(5, int(base_enemy["damage"] * dmg_mult))

    # Защита ранней игры от "ваншот"-баланса.
    if player_level <= 10:
        scaled_hp = min(scaled_hp, 45 + player_level * 10)
        scaled_dmg = min(scaled_dmg, 12 + player_level * 3)

    enemy_speed = max(3, int(10 + enemy_level // 5 + role.get("speed_mod", 0)))

    reward_mult = 1.0 + max(0.0, (enemy_level - zone_level) * 0.06)
    reward_mult *= 1.0 + min(0.35, max(0, rank_tier - 1) * 0.015)
    if is_elite:
        reward_mult += 0.25

    enemy_name = base_enemy["name"]
    if is_elite:
        enemy_name = f"⭐ Элитный {enemy_name}"

    return {
        "enemy_name": enemy_name,
        "enemy_description": base_enemy["description"],
        "enemy_hp": scaled_hp,
        "enemy_max_hp": scaled_hp,
        "enemy_damage": scaled_dmg,
        "enemy_level": enemy_level,
        "enemy_role": role_key,
        "enemy_role_label": role["label"],
        "enemy_speed": enemy_speed,
        "enemy_evade_chance": int(role.get("evade_chance", 0)),
        "enemy_drain_chance": int(role.get("drain_chance", 0)),
        "enemy_drain_min": int(role.get("drain_min", 0)),
        "enemy_drain_max": int(role.get("drain_max", 0)),
        "enemy_is_elite": bool(is_elite),
        "reward_mult": round(reward_mult, 2),
    }


def _roll_initiative(player, enemy_speed: int) -> dict:
    """Бросок инициативы d20 + модификаторы."""
    player_perception = int(getattr(player, "effective_perception", getattr(player, "perception", 0)) or 0)
    player_luck = int(getattr(player, "effective_luck", getattr(player, "luck", 0)) or 0)

    player_roll = random.randint(1, 20)
    enemy_roll = random.randint(1, 20)

    player_total = player_roll + player_perception // 2 + player_luck // 3
    enemy_total = enemy_roll + enemy_speed

    player_first = player_total >= enemy_total

    return {
        "player_roll": player_roll,
        "enemy_roll": enemy_roll,
        "player_total": player_total,
        "enemy_total": enemy_total,
        "player_first": player_first,
    }


def _create_hp_bar(current: int, max_val: int, bar_length: int = 10) -> str:
    """Создать прогресс-бар HP"""
    return ui.bar(current, max_val, width=bar_length, fill="#", empty="-")


def _format_combat_hud(combat: dict, player) -> str:
    enemy_bar = _create_hp_bar(combat['enemy_hp'], combat['enemy_max_hp'], bar_length=14)
    player_bar = _create_hp_bar(player.health, player.max_health, bar_length=14)
    enemy_pct = ui.pct(combat['enemy_hp'], combat['enemy_max_hp'])
    player_pct = ui.pct(player.health, player.max_health)

    lines = [
        ui.section("Статус боя"),
        f"🎯 Враг: {combat['enemy_name']}",
        f"   HP      {enemy_bar} {combat['enemy_hp']}/{combat['enemy_max_hp']} ({enemy_pct}%)",
        f"🧍 Ты",
        f"   HP      {player_bar} {player.health}/{player.max_health} ({player_pct}%)",
        f"   Энергия {ui.bar(player.energy, 100, width=14)} {player.energy}/100",
        f"   Защита  {player.total_defense}",
    ]
    return "\n".join(lines)


def _handle_death(player, vk, user_id: int, cause: str = None, killer_name: str = None, final_damage: int = None):
    """Обработка смерти персонажа в бою с экраном поражения."""
    _, create_location_keyboard, _, _ = _get_main_imports()
    from infra.state_manager import clear_travel_state

    # 1) Экран поражения (до применения штрафов/респавна)
    cause_text = cause or "полученные раны"
    killer_text = f"{killer_name}" if killer_name else "неизвестная угроза"
    damage_text = f"\n💥 Последний урон: {int(final_damage)}" if final_damage is not None else ""
    defeat_message = (
        f"{ui.title('Поражение')}\n"
        f"☠️ Тебя добивает: {killer_text}\n"
        f"📌 Причина: {cause_text}"
        f"{damage_text}\n\n"
        "Сознание меркнет..."
    )
    vk.messages.send(
        user_id=user_id,
        message=defeat_message,
        random_id=0
    )

    # Штрафы при смерти (единые с выбросом): -20% деньги, -15% XP
    lost_money = int(player.money * 0.20)
    lost_exp = int(player.experience * 0.15)

    player.money -= lost_money
    player.experience -= lost_exp
    player.health = player.max_health // 2  # 50% HP
    player.energy = 50

    # Смерть в коридоре должна моментально прерывать путь.
    clear_travel_state(user_id)

    # Перемещаем игрока в больницу после смерти.
    player.current_location_id = "больница"
    database.update_user_location(user_id, "больница")

    database.update_user_stats(
        user_id,
        health=player.health,
        energy=player.energy,
        radiation=0,
        money=player.money,
        experience=player.experience
    )

    message = (
        f"{ui.title('Ты погиб')}\n"
        f"Твоё тело нашли другие сталкеры и принесли в безопасное место.\n\n"
        f"{ui.section('Причина')}\n"
        f"• {cause_text}\n\n"
        f"{ui.section('Потери')}\n"
        f"• Деньги: -{lost_money} руб.\n"
        f"• Опыт: -{lost_exp}\n\n"
        f"{ui.section('Текущее состояние')}\n"
        f"HP      {ui.bar(player.health, player.max_health, width=14)} {player.health}/{player.max_health}\n"
        f"Энергия {ui.bar(player.energy, 100, width=14)} {player.energy}/100\n"
        f"Радиация 0"
    )

    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=create_location_keyboard("больница").get_keyboard(),
        random_id=0
    )


def cancel_research(user_id: int):
    """Отменить исследование"""
    if user_id in _research_timers:
        del _research_timers[user_id]
        clear_research_state(user_id)
        return True
    return False


def is_researching(user_id: int) -> bool:
    """Проверить, идёт ли исследование"""
    return user_id in _research_timers


def get_research_status(user_id: int) -> dict:
    """Получить статус исследования"""
    if user_id not in _research_timers:
        return None

    data = _research_timers[user_id]
    elapsed = time.time() - data["start_time"]
    remaining = max(0, data["time_sec"] - elapsed)

    return {
        "time_sec": data["time_sec"],
        "remaining": int(remaining),
        "location_id": data["location_id"]
    }


def show_explore_menu(player, vk, user_id: int):
    """Показать меню исследования (случайное время)"""
    _, create_location_keyboard, VkKeyboard, VkKeyboardColor = _get_main_imports()

    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Исследовать", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)

    message = (
        f"{ui.title('Исследование локации')}\n"
        f"Нажми 'Исследовать' — время будет выбрано случайно.\n\n"
        f"{ui.section('Режимы')}\n"
        f"5 сек — быстрый поиск (1 энергия)\n"
        f"10 сек — обычный поиск (2 энергии)\n"
        f"15 сек — тщательный поиск (3 энергии)\n\n"
        f"Чем дольше время — тем больше находок, но выше риск.\n\n"
        f"Твоя энергия: {player.energy}/100"
    )

    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=keyboard.get_keyboard(),
        random_id=0
    )


def cleanup_research_timers():
    """Удалить записи таймеров, время которых уже истекло"""
    current_time = time.time()
    expired = [
        uid for uid, data in _research_timers.items()
        if current_time - data["start_time"] > data["time_sec"] + 60  # +60 сек запас
    ]
    for uid in expired:
        del _research_timers[uid]

def handle_explore_time(player, vk, user_id: int, time_sec: int = None):
    cleanup_research_timers()
    """Запустить исследование с таймером (случайное время если не указано)"""
    # Если время не указано - выбираем случайное
    if time_sec is None:
        # Доступные варианты с весами
        time_options = [
            (5, 40),   # 40% шанс - быстрый
            (10, 35),  # 35% шанс - обычный
            (15, 25),  # 25% шанс - тщательный
        ]
        total = sum(w for _, w in time_options)
        rand = random.randint(1, total)
        cumulative = 0
        for t, w in time_options:
            cumulative += w
            if rand <= cumulative:
                time_sec = t
                break
    _combat_state, create_location_keyboard, _, _ = _get_main_imports()

    if player.current_location_id not in RESEARCH_LOCATIONS:
        return

    # Проверка: не идёт ли уже исследование
    if user_id in _research_timers:
        vk.messages.send(
            user_id=user_id,
            message="Исследование уже идёт! Дождись завершения.",
            random_id=0
        )
        return

    # Проверка энергии (с модификатором локации)
    from game.location_mechanics import get_energy_cost_mult
    energy_cost_base = RESEARCH_ENERGY_COST.get(time_sec, 2)
    energy_cost = max(1, int(energy_cost_base * get_energy_cost_mult(player.current_location_id)))
    passive = player._get_passive_bonuses() if hasattr(player, "_get_passive_bonuses") else {}
    research_discount_pct = max(0, min(80, int(passive.get("research_energy_discount_pct", 0) or 0)))
    if research_discount_pct > 0:
        energy_cost = max(1, int(energy_cost * (100 - research_discount_pct) / 100))

    if player.energy < energy_cost:
        vk.messages.send(
            user_id=user_id,
            message=(
                f"Не хватает энергии!\n\n"
                f"Нужно: {energy_cost} энергии\n"
                f"У тебя: {player.energy}/100\n\n"
                f"Восстанови энергию: поешь, выпей кофе или энергетик."
            ),
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    # Тратим энергию
    energy_before = player.energy
    player.energy -= energy_cost
    database.update_user_stats(user_id, energy=player.energy)
    energy_after = player.energy

    # Запускаем таймер исследования
    start_time = time.time()
    location_id = player.current_location_id
    find_chance = player.find_chance
    rare_find_chance = player.rare_find_chance
    current_energy = energy_after

    # Сохраняем состояние исследования
    _research_timers[user_id] = {
        "start_time": start_time,
        "time_sec": time_sec,
        "location_id": location_id,
        "find_chance": find_chance,
        "rare_find_chance": rare_find_chance,
        "remaining_energy": current_energy,
        "player_id": user_id
    }

    # Запускаем фоновый таймер
    timer = threading.Timer(time_sec, _complete_research, args=(user_id, vk, start_time))
    timer.daemon = True
    timer.start()

    # Отправляем сообщение о начале исследования
    multiplier = RESEARCH_TIME_MULTIPLIERS.get(time_sec, {"name": "Поиск", "chance": 1.0, "danger": 1.0})
    scan_name = multiplier.get("name", "Поиск")
    danger_mark = "низкий" if multiplier.get("danger", 1.0) <= 0.8 else "средний" if multiplier.get("danger", 1.0) <= 1.2 else "высокий"
    loc_display_name, mods_info = _build_research_modifiers_info(location_id, time_sec)

    vk.messages.send(
        user_id=user_id,
        message=(
            "═ 🔍 ИССЛЕДОВАНИЕ ЗАПУЩЕНО ═\n\n"
            f"📍 Зона: {loc_display_name}\n"
            f"🧭 Режим: {scan_name}\n"
            f"⏱️ Длительность: {time_sec} сек\n"
            f"⚠️ Риск: {danger_mark}\n"
            f"⚡ Энергия: {energy_before} → {energy_after} (-{energy_cost})\n\n"
            "Активные модификаторы:\n"
            f"{mods_info}\n\n"
            "Сканирую местность...\n"
            "Результат придёт автоматически."
        ),
        random_id=0
    )


def _complete_research(user_id: int, vk, expected_start_time: float):
    """Завершение исследования по таймеру"""
    # Проверяем, не отменено ли исследование
    if user_id not in _research_timers:
        return

    data = _research_timers[user_id]

    # Проверяем, что это тот же таймер (не перезапущен)
    if data["start_time"] != expected_start_time:
        return

    time_sec = data["time_sec"]
    location_id = data["location_id"]
    find_chance = data["find_chance"]
    rare_find_chance = data["rare_find_chance"]
    remaining_energy = data["remaining_energy"]

    # Удаляем из активных исследований
    del _research_timers[user_id]

    # Получаем множители
    multiplier = RESEARCH_TIME_MULTIPLIERS[time_sec]
    chance_mult = multiplier['chance']
    danger_mult = multiplier['danger']

    # Выбираем событие (с модификаторами локации)
    event = _select_research_event_by_chance(
        find_chance,
        chance_mult,
        danger_mult,
        location_id,
        user_id=user_id,
    )

    # Используем полноценного Player, чтобы боевая система получала все атрибуты
    # (total_defense, dodge_chance, max_health, инициатива и т.д.).
    from models.player import Player
    temp_player = Player(user_id)
    temp_player.current_location_id = location_id
    temp_player.energy = remaining_energy

    # Обрабатываем событие
    _handle_research_event(temp_player, vk, user_id, event, time_sec)

    # === Уникальные механики локаций ===
    _check_location_unique_mechanics(temp_player, location_id, event, vk, user_id)


def _check_location_unique_mechanics(player, location_id: str, event_id: str, vk, user_id: int):
    """Проверить и применить уникальные механики локаций после исследования"""
    from game.location_mechanics import (
        check_ambush, check_zone_mutation, check_mutant_hunt,
        get_mutant_hunt_count,
    )
    _, create_location_keyboard, VkKeyboard, VkKeyboardColor = _get_main_imports()
    _combat_state_ref, _, _, _ = _get_main_imports()

    # === Военная дорога: ЗАСАДА ===
    if check_ambush(location_id):
        vk.messages.send(
            user_id=user_id,
            message=(
                "💀 **ЗАСАДА!**\n\n"
                "Ты попал в военную засаду! Солдаты заметили тебя...\n"
                "Будет бой — но награда стоит риска.\n\n"
                "⚔️ Лут после победы: x2"
            ),
            random_id=0,
        )
        # Запускаем бой с засадой — модифицируем состояние
        # Удвоенный лут будет обработан в _handle_enemy_loot
        combat_data = _combat_state_ref.get(user_id)
        if combat_data:
            combat_data["ambush"] = True  # Флаг для удвоенного лута
        else:
            # Если базовый исход исследования был не "enemy", засада всё равно должна запустить бой.
            _spawn_enemy(player, vk, user_id, enemy_type="military", allow_elite=False)
            combat_data = _combat_state_ref.get(user_id)
            if combat_data:
                combat_data["ambush"] = True

    # === НИИ: МУТАЦИЯ ЗОНЫ ===
    mutation = check_zone_mutation(location_id)
    if mutation and mutation.get("active"):
        vk.messages.send(
            user_id=user_id,
            message=mutation["message"],
            random_id=0,
        )

    # === Заражённый лес: ОХОТА МУТАНТОВ ===
    if check_mutant_hunt() and event_id and "enemy" in str(RESEARCH_EVENTS.get(event_id, {}).get("type", "")):
        hunt_count = get_mutant_hunt_count()
        vk.messages.send(
            user_id=user_id,
            message=(
                f"🐺 **ОХОТА МУТАНТОВ!**\n\n"
                "Ты убил мутанта, но его сородичи пришли мстить!\n"
                f"Стая из {hunt_count} мутантов атакует тебя!\n\n"
                "Приготовься к бою!"
            ),
            random_id=0,
        )
        # Запускаем дополнительный бой
        # (будет обработано через состояние боя)
        if _combat_state_ref.get(user_id):
            _combat_state_ref[user_id]["mutant_hunt"] = hunt_count


def _select_research_event_by_chance(
    find_chance: float,
    chance_mult: float,
    danger_mult: float,
    location_id: str = None,
    user_id: int | None = None,
):
    """Выбрать событие исследования на основе шансов и модификаторов локации"""
    from game.location_mechanics import get_event_weights, get_find_chance_mult, get_danger_mult
    from game.limited_events import get_limited_event_modifiers

    no_anomaly_streak = 0
    if user_id is not None:
        no_anomaly_streak = int(database.get_user_flag(user_id, ANOMALY_GUARANTEE_FLAG, 0) or 0)
        if no_anomaly_streak >= ANOMALY_GUARANTEE_RESEARCHES - 1:
            database.set_user_flag(user_id, ANOMALY_GUARANTEE_FLAG, 0)
            return "anomaly"

    # Применяем модификаторы локации
    loc_find_mult = get_find_chance_mult(location_id) if location_id else 1.0
    loc_danger_mult = get_danger_mult(location_id) if location_id else 1.0
    loc_event_weights = get_event_weights(location_id) if location_id else {}
    limited_mods = get_limited_event_modifiers()
    limited_find_mult = float(limited_mods.get("research_find_mult", 1.0) or 1.0)
    limited_danger_mult = float(limited_mods.get("research_danger_mult", 1.0) or 1.0)
    limited_artifact_mult = float(limited_mods.get("artifact_event_mult", 1.0) or 1.0)
    limited_enemy_mult = float(limited_mods.get("enemy_event_mult", 1.0) or 1.0)

    # Базовый шанс найти что-то (с модификатором локации)
    base_find_chance = min(95, find_chance * chance_mult * 1.5 * loc_find_mult * limited_find_mult)  # max 95%

    # Проверяем, нашли ли что-то
    if random.randint(1, 100) > base_find_chance:
        if user_id is not None:
            database.set_user_flag(user_id, ANOMALY_GUARANTEE_FLAG, no_anomaly_streak + 1)
        return "nothing"

    # Выбираем событие
    weights = []
    event_ids = []

    for event_id, event_data in RESEARCH_EVENTS.items():
        if event_id == "nothing":
            continue

        base_chance = event_data["chance"]

        if event_data.get("danger", 0) > 0:
            weight = base_chance * danger_mult * loc_danger_mult * limited_danger_mult
        else:
            weight = base_chance * chance_mult

        # Применяем веса локации (если есть)
        if loc_event_weights:
            # Проверяем прямой вес для этого события
            loc_weight = loc_event_weights.get(event_id)
            if loc_weight is not None:
                weight *= loc_weight
            # Проверяем общий вес для типа события (например "enemy")
            event_type = event_data.get("type")
            if event_type and event_type in loc_event_weights:
                weight *= loc_event_weights[event_type]

        event_type = str(event_data.get("type") or "")
        if event_type in {"enemy"}:
            weight *= limited_enemy_mult
        if event_type in {"artifact", "artifact_cluster"}:
            weight *= limited_artifact_mult

        weights.append(weight)
        event_ids.append(event_id)

    total_weight = sum(weights)
    if total_weight == 0:
        return "nothing"

    rand = random.uniform(0, total_weight)
    cumulative = 0

    selected = "nothing"
    for i, weight in enumerate(weights):
        cumulative += weight
        if rand <= cumulative:
            selected = event_ids[i]
            break

    if user_id is not None:
        if selected == "anomaly":
            database.set_user_flag(user_id, ANOMALY_GUARANTEE_FLAG, 0)
        else:
            database.set_user_flag(user_id, ANOMALY_GUARANTEE_FLAG, no_anomaly_streak + 1)

    return selected


def _select_research_event(player, chance_mult: float, danger_mult: float):
    """Выбрать событие исследования на основе шансов"""
    # Базовый шанс найти что-то
    find_chance = player.find_chance * chance_mult

    # Проверяем, нашли ли что-то
    if random.randint(1, 100) > find_chance:
        return "nothing"

    # Выбираем событие с учетом danger_mult
    weights = []
    event_ids = []

    for event_id, event_data in RESEARCH_EVENTS.items():
        if event_id == "nothing":
            continue

        base_chance = event_data["chance"]

        # Модифицируем шанс в зависимости от типа
        if event_data.get("danger", 0) > 0:
            # Опасные события чаще при большем danger_mult
            weight = base_chance * danger_mult
        else:
            # Находки чаще при большем chance_mult
            weight = base_chance * chance_mult

        weights.append(weight)
        event_ids.append(event_id)

    # Выбираем событие по весам
    total_weight = sum(weights)
    if total_weight == 0:
        return "nothing"

    rand = random.uniform(0, total_weight)
    cumulative = 0

    for i, weight in enumerate(weights):
        cumulative += weight
        if rand <= cumulative:
            return event_ids[i]

    return "nothing"


def _handle_research_event(player, vk, user_id: int, event_id: str, time_sec: int):
    """Обработать событие исследования"""
    _combat_state, create_location_keyboard, _, _ = _get_main_imports()

    event = RESEARCH_EVENTS.get(event_id, RESEARCH_EVENTS["nothing"])
    event_type = event.get("type", "nothing")

    if event_type == "nothing":
        vk.messages.send(
            user_id=user_id,
            message=f"Ты исследовал локацию {time_sec} секунд...\n\n{event['message']}\n\nЭнергия потрачена.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    if event_type == "item":
        _spawn_item(player, vk, user_id)
        return

    if event_type == "artifact":
        _spawn_artifact(player, vk, user_id)
        return

    if event_type == "enemy":
        _spawn_enemy(player, vk, user_id, event.get("enemy_type"))
        return

    if event_type == "anomaly":
        _handle_anomaly(player, vk, user_id)
        return

    if event_type == "radiation":
        _handle_radiation(player, vk, user_id)
        return

    if event_type == "trap":
        _handle_trap(player, vk, user_id)
        return

    if event_type == "stash":
        _handle_stash(player, vk, user_id)
        return

    if event_type == "survivor":
        _handle_survivor(player, vk, user_id)
        return

    if event_type == "shell_cache":
        _handle_shell_cache(player, vk, user_id)
        return

    if event_type == "intel":
        _handle_intel_find(player, vk, user_id)
        return

    if event_type == "camp":
        _handle_abandoned_camp(player, vk, user_id)
        return

    if event_type == "artifact_cluster":
        _handle_artifact_cluster(player, vk, user_id)
        return

    if event_type == "psi":
        _handle_psi_echo(player, vk, user_id)
        return

    if event_type == "trail":
        _handle_blood_trail(player, vk, user_id)
        return


def _apply_blind_anomaly_loss(user_id: int, player) -> str:
    """
    Потери при попадании в аномалию без детектора.
    Пытаемся списать гильзы/предмет/деньги.
    """
    # 1) Гильзы
    shells = int(database.get_user_shells(user_id) or 0)
    if shells > 0:
        loss = min(shells, random.randint(1, 3))
        if database.remove_shells(user_id, loss):
            return f"🎯 Потеряно гильз: {loss}"

    # 2) Случайный НЕэкипированный предмет
    try:
        equipped_names = {
            getattr(player, "equipped_weapon", None),
            getattr(player, "equipped_backpack", None),
            getattr(player, "equipped_device", None),
            getattr(player, "equipped_armor", None),
            getattr(player, "equipped_armor_head", None),
            getattr(player, "equipped_armor_body", None),
            getattr(player, "equipped_armor_legs", None),
            getattr(player, "equipped_armor_hands", None),
            getattr(player, "equipped_armor_feet", None),
        }
        equipped_names.update(set(getattr(player, "equipped_artifacts", []) or []))
        inv = database.get_user_inventory(user_id) or []
        candidates = [it for it in inv if int(it.get("quantity", 0) or 0) > 0 and it.get("name") not in equipped_names]
        if candidates and random.randint(1, 100) <= ANOMALY_BLIND_ITEM_LOSS_CHANCE:
            lost = random.choice(candidates)
            lost_name = str(lost.get("name") or "предмет")
            if database.remove_item_from_inventory(user_id, lost_name, 1):
                try:
                    player.inventory.reload()
                except Exception:
                    pass
                return f"📦 Потерян предмет: {lost_name}"
    except Exception:
        pass

    # 3) Деньги (fallback)
    lose_money = random.randint(50, 180)
    current_money = int(getattr(player, "money", 0) or 0)
    actual = min(current_money, lose_money)
    if actual > 0:
        new_money = current_money - actual
        database.update_user_stats(user_id, money=new_money)
        player.money = new_money
        return f"💰 Потеряно денег: {actual} руб."

    return "⚠️ Потерь по ресурсам нет, повезло."


def _handle_anomaly(player, vk, user_id: int):
    """Обработка попадания в аномалию"""
    import anomalies as anomalies_module
    from infra.state_manager import set_anomaly_state
    _, create_location_keyboard, VkKeyboard, VkKeyboardColor = _get_main_imports()

    # Получаем данные игрока
    user = database.get_user_by_vk(user_id)
    if not user:
        return

    # Проверяем детектор: без него аномалия всё равно встречается,
    # но информация хуже и риски выше.
    detector = anomalies_module.get_equipped_detector(player)

    # Получаем случайную аномалию (с учётом локации)
    from game.location_mechanics import get_random_anomaly_for_location
    anomaly = get_random_anomaly_for_location(player.current_location_id)
    anomaly_type = anomaly["type"]
    anomaly_name = anomaly["name"]
    anomaly_icon = anomaly["icon"]
    anomaly_desc = anomaly["description"]
    anomaly_danger = anomaly["danger_level"]

    # Данные детектора / урон
    has_detector = bool(detector)
    detector_bonus = anomalies_module.get_detector_bonus(player) if has_detector else 0
    detector_name = detector["name"] if has_detector else "нет"
    if has_detector:
        damage_min, damage_max = anomaly.get("damage_with_detector", [5, 15])
    else:
        damage_min, damage_max = anomaly.get("damage_without_detector", [20, 45])

    # Возможные артефакты в этой аномалии
    possible_artifacts = anomaly.get("artifacts", [])

    # Получаем количество гильз
    shells = database.get_user_shells(user_id)

    # Без детектора можно "влететь" в аномалию: мгновенный урон и потери.
    blind_intro = ""
    if not has_detector and random.randint(1, 100) <= ANOMALY_BLIND_MISSTEP_CHANCE:
        blind_damage = random.randint(damage_min, damage_max)
        new_health = max(0, int(user.get("health", 0)) - blind_damage)
        database.update_user_stats(user_id, health=new_health)
        player.health = new_health
        lost_text = _apply_blind_anomaly_loss(user_id, player)
        if new_health <= 0:
            _handle_death(
                player,
                vk,
                user_id,
                cause=f"Смертельный контакт с аномалией ({anomaly_name})",
                killer_name=anomaly_name,
                final_damage=blind_damage,
            )
            return
        blind_intro = (
            "☠️ ВСЛЕПУЮ В АНОМАЛИЮ\n\n"
            "Ты поздно заметил аномальный контур и угодил прямо в активную зону.\n"
            f"Получен урон: {blind_damage}\n"
            f"❤️ HP: {new_health}/{int(getattr(player, 'max_health', 100) or 100)}\n"
            f"{lost_text}\n\n"
        )

    # Сохраняем состояние аномалии в централизованный state_manager
    set_anomaly_state(user_id, {
        "anomaly_type": anomaly_type,
        "anomaly_name": anomaly_name,
        "anomaly_icon": anomaly_icon,
        "damage_min": damage_min,
        "damage_max": damage_max,
        "possible_artifacts": possible_artifacts,
        "detector": detector_name,
        "detector_bonus": detector_bonus,
        "location_id": player.current_location_id
    })

    # Формируем сообщение
    message = (
        f"⚠️ АНОМАЛИЯ ОБНАРУЖЕНА! ⚠️\n\n"
        f"{anomaly_icon} {anomaly_name if has_detector else 'Неопознанная аномалия'}\n"
        f"{anomaly_desc if has_detector else 'Без детектора контур нестабилен, тип трудно определить.'}\n\n"
        f"Опасность: {anomaly_danger}{' (повышенная без детектора)' if not has_detector else ''}\n"
        f"Детектор: {detector_name}"
        f"{f' (+{detector_bonus}% к шансу)' if has_detector else ' (бонус 0%)'}\n"
        f"Гильзы: {shells} шт.\n"
    )
    if blind_intro:
        message = blind_intro + message

    if possible_artifacts and has_detector:
        message += f"Возможные артефакты: {', '.join(possible_artifacts)}\n"
    elif not has_detector:
        message += "Возможные артефакты: неизвестно (нужен детектор).\n"

    message += "\nВыбери действие:"

    # Клавиатура выбора
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Обойти", color=VkKeyboardColor.POSITIVE)
    if shells > 0:
        keyboard.add_button("Бросить гильзу", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Отступить", color=VkKeyboardColor.NEGATIVE)

    if shells == 0:
        message += "\n\n⚠️ У тебя нет гильз! Сначала найди гильзы."
    if not has_detector:
        message += "\n⚠️ Без детектора шанс добычи ниже, а урон при ошибке выше."

    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=keyboard.get_keyboard(),
        random_id=0
    )


def handle_anomaly_action(player, vk, user_id: int, action: str):
    """Обработка действия игрока с аномалией"""
    import anomalies as anomalies_module
    from infra.state_manager import get_anomaly_data, clear_anomaly_state, set_pending_loot_choice

    _, create_location_keyboard, VkKeyboard, VkKeyboardColor = _get_main_imports()

    # Получаем состояние аномалии
    anomaly_data = get_anomaly_data(user_id)
    if not anomaly_data:
        return

    anomaly_type = anomaly_data["anomaly_type"]
    anomaly_name = anomaly_data["anomaly_name"]
    anomaly_icon = anomaly_data["anomaly_icon"]
    damage_min = anomaly_data["damage_min"]
    damage_max = anomaly_data["damage_max"]
    possible_artifacts = anomaly_data["possible_artifacts"]
    location_id = anomaly_data["location_id"]

    user = database.get_user_by_vk(user_id)
    if not user:
        return

    # Удаляем состояние аномалии
    clear_anomaly_state(user_id)

    if action == "обойти":
        # Попытка обойти - зависит от восприятия
        perception = int(getattr(player, "effective_perception", user.get('perception', 1)) or 1)
        dodge_chance = min(95, 30 + perception * 5)

        if random.randint(1, 100) <= dodge_chance:
            vk.messages.send(
                user_id=user_id,
                message=(
                    f"{anomaly_icon} ОБХОД\n\n"
                    f"Ты аккуратно обошёл аномалию '{anomaly_name}'.\n\n"
                    f"Твоё восприятие помогло найти безопасный путь.\n\n"
                    f"Никаких потерь."
                ),
                keyboard=create_location_keyboard(location_id).get_keyboard(),
                random_id=0
            )
        else:
            # Не удалось обойти - получаем урон
            damage = random.randint(damage_min, damage_max)
            new_health = max(0, user['health'] - damage)
            database.update_user_stats(user_id, health=new_health)
            player.health = new_health
            if new_health <= 0:
                _handle_death(
                    player,
                    vk,
                    user_id,
                    cause=f"Неудачный обход аномалии ({anomaly_name})",
                    killer_name=anomaly_name,
                    final_damage=damage,
                )
                return

            max_hp = int(getattr(player, "max_health", 100) or 100)
            vk.messages.send(
                user_id=user_id,
                message=(
                    f"{anomaly_icon} НЕУДАЧНЫЙ ОБХОД\n\n"
                    f"Не удалось обойти аномалию '{anomaly_name}'!\n\n"
                    f"Получен урон: {damage}\n"
                    f"Текущее HP: {new_health}/{max_hp}"
                ),
                keyboard=create_location_keyboard(location_id).get_keyboard(),
                random_id=0
            )

    elif action in {"бросить гильзу", "добыть", "извлечь"}:
        # === НОВАЯ МЕХАНИКА: бросок гильзы ===
        shells = database.get_user_shells(user_id)

        if shells <= 0:
            # Нет гильз - показываем сообщение и возвращаем в меню аномалии
            vk.messages.send(
                user_id=user_id,
                message=(
                    f"{anomaly_icon} НЕТ ГИЛЬЗ!\n\n"
                    f"У тебя нет гильз для добычи артефакта.\n\n"
                    f"Сначала найди гильзы (выпадают с врагов или покупаются)."
                ),
                keyboard=create_location_keyboard(location_id).get_keyboard(),
                random_id=0
            )
            return

        # Тратим одну гильзу
        database.remove_shells(user_id, 1)
        shells_after = shells - 1

        # Получаем бонус детектора
        detector = anomalies_module.get_equipped_detector(player)
        detector_bonus = anomalies_module.get_detector_bonus(player) if detector else 0

        # Бросок гильзы - пытаемся получить артефакт
        luck = int(getattr(player, "effective_luck", user.get('luck', 5)) or 5)
        from game.emission import get_emission_artifact_bonus
        artifact_bonus_mult = get_emission_artifact_bonus()
        result = database.roll_artifact_from_anomaly(
            anomaly_type,
            luck,
            detector_bonus,
            chance_multiplier=artifact_bonus_mult,
        )

        if result:
            # Артефакт получен!
            artifact_name = result["name"]
            rarity = result["rarity"]
            artifact_item = database.get_item_by_name(artifact_name) or {
                "name": artifact_name,
                "category": "artifacts",
                "rarity": rarity,
                "description": "Описание отсутствует."
            }

            # Формируем сообщение об успехе
            rarity_emoji = {
                "common": "⚪",
                "rare": "🔵",
                "unique": "🟣",
                "legendary": "🟡"
            }.get(rarity, "⚪")

            # Ожидаем решение игрока: оставить или выбросить
            set_pending_loot_choice(user_id, {
                "item_type": "artifact",
                "item_name": artifact_name,
                "location_id": location_id,
                "shells_after": shells_after,
            })

            from handlers.inventory import build_item_details
            details = build_item_details(artifact_item)

            choice_keyboard = VkKeyboard(one_time=False)
            choice_keyboard.add_button("Оставить", color=VkKeyboardColor.POSITIVE)
            choice_keyboard.add_button("Выбросить", color=VkKeyboardColor.NEGATIVE)

            vk.messages.send(
                user_id=user_id,
                message=(
                    f"{anomaly_icon} ✨ АРТЕФАКТ ПОЛУЧЕН! ✨\n\n"
                    f"Ты бросил гильзу в аномалию '{anomaly_name}'...\n\n"
                    f"{rarity_emoji}{artifact_name}\n"
                    f"Редкость: {rarity}\n\n"
                    f"Гильз осталось: {shells_after}\n\n"
                    f"{details}\n\n"
                    f"Реши, что делать с находкой:"
                ),
                keyboard=choice_keyboard.get_keyboard(),
                random_id=0
            )
        else:
            # Артефакт не выпал - гильза потеряна
            vk.messages.send(
                user_id=user_id,
                message=(
                    f"{anomaly_icon} ПОПЫТКА ДОБЫЧИ\n\n"
                    f"Ты бросил гильзу в аномалию '{anomaly_name}'...\n\n"
                    f"Гильза сгорела в аномалии!\n"
                    f"Артефакт не выпал.\n\n"
                    f"Гильз осталось: {shells_after}"
                ),
                keyboard=create_location_keyboard(location_id).get_keyboard(),
                random_id=0
            )

    elif action == "отступить":
        # Гарантированный урон при отступлении
        damage = random.randint(damage_min, damage_max)
        new_health = max(0, user['health'] - damage)
        database.update_user_stats(user_id, health=new_health)
        player.health = new_health
        if new_health <= 0:
            _handle_death(
                player,
                vk,
                user_id,
                cause=f"Отступление из аномалии ({anomaly_name})",
                killer_name=anomaly_name,
                final_damage=damage,
            )
            return

        max_hp = int(getattr(player, "max_health", 100) or 100)
        vk.messages.send(
            user_id=user_id,
            message=(
                f"{anomaly_icon} ОТСТУПЛЕНИЕ\n\n"
                f"Ты решил отступить от аномалии '{anomaly_name}'.\n\n"
                f"При отступлении аномалия нанесла удар:\n"
                f"Получен урон: {damage}\n"
                f"Текущее HP: {new_health}/{max_hp}"
            ),
            keyboard=create_location_keyboard(location_id).get_keyboard(),
            random_id=0
        )


def _handle_radiation(player, vk, user_id: int):
    """Обработка радиоактивного заражения (с модификатором локации)"""
    from game.location_mechanics import get_radiation_mult
    from models.player import calculate_radiation_hp_loss, format_radiation_rate, get_radiation_stage
    _, create_location_keyboard, _, _ = _get_main_imports()

    # Получаем реальные данные игрока
    user = database.get_user_by_vk(user_id)
    if not user:
        return

    rad_mult = get_radiation_mult(player.current_location_id)
    rad_damage = int(random.randint(15, 35) * rad_mult)
    rad_gain = int(random.randint(10, 25) * rad_mult)
    passive = player._get_passive_bonuses() if hasattr(player, "_get_passive_bonuses") else {}
    rad_reduction_pct = max(0, min(80, int(passive.get("radiation_reduction_pct", 0) or 0)))
    if rad_reduction_pct > 0:
        rad_damage = max(0, int(rad_damage * (100 - rad_reduction_pct) / 100))
        rad_gain = max(0, int(rad_gain * (100 - rad_reduction_pct) / 100))
    new_radiation = user['radiation'] + rad_gain
    rad_overload = calculate_radiation_hp_loss(new_radiation, user['health'])
    total_rad_damage = rad_damage + rad_overload
    new_health = max(0, user['health'] - total_rad_damage)

    database.update_user_stats(user_id, health=new_health, radiation=new_radiation)
    player.health = new_health
    player.radiation = new_radiation
    if new_health <= 0:
        _handle_death(
            player,
            vk,
            user_id,
            cause="Критическое радиационное поражение",
            killer_name="радиация",
            final_damage=total_rad_damage,
        )
        return

    rad_mult_text = f" (x{rad_mult:.1f} зона)" if rad_mult != 1.0 else ""
    rad_reduction_text = f"\nСопротивление класса: -{rad_reduction_pct}%" if rad_reduction_pct > 0 else ""
    stage = get_radiation_stage(new_radiation)

    max_hp = int(getattr(player, "max_health", 100) or 100)
    vk.messages.send(
        user_id=user_id,
        message=(
            f"РАДИАЦИЯ!\n\n"
            f"Ты вошёл в зону повышенной радиации!{rad_mult_text}{rad_reduction_text}\n\n"
            f"Базовый урон: {rad_damage}\n"
            f"Токсичность накопления: {rad_overload}\n"
            f"Итоговый урон: {total_rad_damage}\n"
            f"Радиация: +{rad_gain}\n"
            f"☢️ Текущая радиация: {new_radiation} ед. ({format_radiation_rate(new_radiation)})\n"
            f"🧪 Стадия: {stage['name']}\n"
            f"HP: {new_health}/{max_hp}"
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _handle_trap(player, vk, user_id: int):
    """Обработка ловушки"""
    _, create_location_keyboard, _, _ = _get_main_imports()

    # Получаем реальные данные игрока
    user = database.get_user_by_vk(user_id)
    if not user:
        return

    damage = random.randint(15, 30)
    new_health = max(0, user['health'] - damage)
    database.update_user_stats(user_id, health=new_health)
    player.health = new_health
    if new_health <= 0:
        _handle_death(
            player,
            vk,
            user_id,
            cause="Смертельная ловушка",
            killer_name="ловушка",
            final_damage=damage,
        )
        return

    max_hp = int(getattr(player, "max_health", 100) or 100)
    vk.messages.send(
        user_id=user_id,
        message=(
            f"ЛОВУШКА!\n\n"
            f"Ты задел растяжку! Раздался щелчок...\n\n"
            f"Получен урон: {damage}\n"
            f"Текущее HP: {new_health}/{max_hp}"
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _handle_stash(player, vk, user_id: int):
    """Обработка тайника сталкера"""
    _, create_location_keyboard, _, _ = _get_main_imports()

    # Получаем реальные данные игрока
    user = database.get_user_by_vk(user_id)
    if not user:
        return

    money = random.randint(50, 200)
    new_money = user['money'] + money
    database.update_user_stats(user_id, money=new_money)
    lvl = max(1, int(getattr(player, "level", 1) or 1))
    supply_item = None
    supply_chance = 100 if lvl <= 10 else 55
    if random.randint(1, 100) <= supply_chance:
        supply_pool = ["Бинт", "Лечебная трава", "Вода"]
        if lvl <= 10:
            supply_pool += ["Бинт", "Аптечка"]
        supply_item = random.choice(supply_pool)
        database.add_item_to_inventory(user_id, supply_item, 1)
        try:
            player.inventory.reload()
        except Exception:
            pass

    supply_text = f"\nПрипасы: {supply_item} x1" if supply_item else ""
    vk.messages.send(
        user_id=user_id,
        message=(
            f"ТАЙНИК СТАЛКЕРА!\n\n"
            f"Ты нашёл спрятанный тайник с припасами!\n\n"
            f"Найдено: {money} руб.\n"
            f"Твой баланс: {new_money} руб."
            f"{supply_text}"
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _handle_survivor(player, vk, user_id: int):
    """Обработка встречи с выжившим"""
    _, create_location_keyboard, _, _ = _get_main_imports()

    # Даём небольшой бонус
    items = ["Бинт", "Аптечка", "Энергетик", "Хлеб", "Вода"]
    item = random.choice(items)
    database.add_item_to_inventory(user_id, item, 1)

    vk.messages.send(
        user_id=user_id,
        message=(
            f"ВЫЖИВШИЙ СТАЛКЕР\n\n"
            f"Ты встретил другого сталкера. Он обрадовался живому лицу.\n\n"
            f"Он поделился с тобой: {item}\n\n"
            f"'Удачи, братан. В Зоне каждый сам за себя.'"
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _handle_shell_cache(player, vk, user_id: int):
    """Военный ящик с гильзами."""
    _, create_location_keyboard, _, _ = _get_main_imports()

    shells_found = random.randint(2, 9)
    success, msg = database.add_shells(user_id, shells_found)
    shells_info = database.get_shells_info(user_id)

    if success:
        text = (
            "📦 ВОЕННЫЙ ЯЩИК\n\n"
            "Под брезентом ты нашёл вскрытый армейский контейнер.\n\n"
            f"Получено гильз: +{shells_found}\n"
            f"Текущий запас: {shells_info['current']}/{shells_info['capacity']}"
        )
    else:
        text = (
            "📦 ВОЕННЫЙ ЯЩИК\n\n"
            "Контейнер оказался полон гильз, но места в мешке не хватило.\n\n"
            f"{msg}\n"
            f"Текущий запас: {shells_info['current']}/{shells_info['capacity']}"
        )

    vk.messages.send(
        user_id=user_id,
        message=text,
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _handle_intel_find(player, vk, user_id: int):
    """Находка данных/документов: деньги + опыт."""
    _, create_location_keyboard, _, _ = _get_main_imports()

    money_gain = random.randint(90, 240)
    exp_gain = _scale_xp_reward(random.randint(8, 20), player, source="research")
    player.money = int(player.money) + money_gain
    gained_xp = int(player.add_experience(exp_gain))
    database.update_user_stats(user_id, money=player.money)

    vk.messages.send(
        user_id=user_id,
        message=(
            "🧾 РАЗВЕДДАННЫЕ\n\n"
            "Ты нашёл планшет с маршрутами патрулей и координатами схронов.\n"
            "Информация ушла перекупщику по защищённому каналу.\n\n"
            f"💰 Деньги: +{money_gain}\n"
            f"📘 Опыт: +{gained_xp}"
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _handle_abandoned_camp(player, vk, user_id: int):
    """Заброшенный лагерь: мелкий лут и восстановление энергии."""
    _, create_location_keyboard, _, _ = _get_main_imports()
    user = database.get_user_by_vk(user_id)
    if not user:
        return

    reward_pool = ["Бинт", "Аптечка", "Вода", "Энергетик", "Хлеб", "Антирад"]
    item = random.choice(reward_pool)
    database.add_item_to_inventory(user_id, item, 1)

    old_energy = int(user.get("energy", 0))
    energy_gain = random.randint(6, 14)
    new_energy = min(100, old_energy + energy_gain)
    database.update_user_stats(user_id, energy=new_energy)
    player.energy = new_energy

    vk.messages.send(
        user_id=user_id,
        message=(
            "⛺ БРОШЕННЫЙ ЛАГЕРЬ\n\n"
            "В лагере тихо, но запасы ещё остались.\n\n"
            f"📦 Найдено: {item} x1\n"
            f"⚡ Энергия: {old_energy} → {new_energy} (+{new_energy - old_energy})"
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _handle_artifact_cluster(player, vk, user_id: int):
    """Скопление артефактов: 1-2 артефакта за событие."""
    _, create_location_keyboard, _, _ = _get_main_imports()
    artifacts = database.get_items_by_category('artifacts')
    if not artifacts:
        _spawn_artifact(player, vk, user_id)
        return

    from handlers.quests import track_quest_artifact

    count = 2 if random.random() < 0.35 else 1
    found = []
    for _ in range(count):
        artifact = random.choice(artifacts)
        found.append(artifact["name"])
        database.add_item_to_inventory(user_id, artifact["name"], 1)
        track_quest_artifact(user_id, vk=vk)

    vk.messages.send(
        user_id=user_id,
        message=(
            "💎 СКОПЛЕНИЕ АРТЕФАКТОВ\n\n"
            "Ты зашёл в нестабильную зону и быстро собрал трофеи.\n\n"
            f"Получено: {', '.join(found)}"
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _handle_psi_echo(player, vk, user_id: int):
    """Пси-эхо: контрольный негативный ивент без боя."""
    _, create_location_keyboard, _, _ = _get_main_imports()
    user = database.get_user_by_vk(user_id)
    if not user:
        return

    hp_loss = random.randint(6, 14)
    energy_loss = random.randint(8, 16)
    rad_gain = random.randint(3, 9)

    old_hp = int(user.get("health", 100))
    old_energy = int(user.get("energy", 0))
    old_rad = int(user.get("radiation", 0))

    new_hp = max(1, old_hp - hp_loss)
    new_energy = max(0, old_energy - energy_loss)
    new_rad = min(100, old_rad + rad_gain)
    database.update_user_stats(user_id, health=new_hp, energy=new_energy, radiation=new_rad)

    player.health = new_hp
    player.energy = new_energy
    player.radiation = new_rad

    vk.messages.send(
        user_id=user_id,
        message=(
            "🧠 ПСИ-ЭХО\n\n"
            "В голове зазвенело, как будто кто-то чужой шепчет рядом.\n\n"
            f"❤️ HP: {old_hp} → {new_hp} (-{old_hp - new_hp})\n"
            f"⚡ Энергия: {old_energy} → {new_energy} (-{old_energy - new_energy})\n"
            f"☢️ Радиация: {old_rad} → {new_rad} (+{new_rad - old_rad})"
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _handle_blood_trail(player, vk, user_id: int):
    """Кровавый след: иногда бой, иногда награда."""
    _, create_location_keyboard, _, _ = _get_main_imports()
    if random.random() < 0.58:
        vk.messages.send(
            user_id=user_id,
            message=(
                "🩸 КРОВАВЫЙ СЛЕД\n\n"
                "След оказался свежим. Хищник рядом.\n"
                "Ты едва успел снять оружие с предохранителя..."
            ),
            random_id=0
        )
        _spawn_enemy(player, vk, user_id, enemy_type="mutant", allow_elite=False)
        return

    user = database.get_user_by_vk(user_id)
    if not user:
        return
    money = random.randint(70, 180)
    new_money = int(user.get("money", 0)) + money
    database.update_user_stats(user_id, money=new_money)
    database.add_item_to_inventory(user_id, "Бинт", 1)

    vk.messages.send(
        user_id=user_id,
        message=(
            "🩸 КРОВАВЫЙ СЛЕД\n\n"
            "Хищник уже ушёл. В кустах ты нашёл рюкзак прошлого сталкера.\n\n"
            f"💰 Найдено: {money} руб.\n"
            "📦 Дополнительно: Бинт x1"
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def _spawn_artifact(player, vk, user_id: int):
    """Спавн артефакта"""
    _, create_location_keyboard, _, _ = _get_main_imports()

    # Получаем случайный артефакт
    artifacts = database.get_items_by_category('artifacts')
    if not artifacts:
        vk.messages.send(
            user_id=user_id,
            message="Ты обыскал территорию...\n\nАртефактов не найдено.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    artifact = random.choice(artifacts)
    database.add_item_to_inventory(user_id, artifact['name'], 1)
    from handlers.quests import track_quest_artifact
    track_quest_artifact(user_id, vk=vk)

    vk.messages.send(
        user_id=user_id,
        message=(
            f"АРТЕФАКТ!\n\n"
            f"Ты нашёл редкий артефакт: {artifact['name']}!\n\n"
            f"{artifact['description']}\n\n"
            f"Добавлено в инвентарь."
        ),
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def handle_explore(player, vk, user_id: int):
    """Исследовать локацию - показать меню выбора времени"""
    show_explore_menu(player, vk, user_id)


def _handle_found_something(player, vk, user_id: int):
    """Обработка найденного предмета/врага"""
    encounter_type = random.randint(1, 100)
    
    if encounter_type <= 50:
        _spawn_enemy(player, vk, user_id)
    else:
        _spawn_item(player, vk, user_id)


def _spawn_enemy(player, vk, user_id: int, enemy_type: str = None, allow_elite: bool = True):
    """Спавн врага"""
    _combat_state, create_location_keyboard, VkKeyboard, VkKeyboardColor = _get_main_imports()
    from game.emission import is_emission_rare_enemy_bonus
    from game.limited_events import get_limited_event_modifiers, get_active_limited_event

    # Если указан тип врага - используем его, иначе - случайный для локации
    if enemy_type:
        # В приоритете враг нужного типа в ТЕКУЩЕЙ локации.
        enemy = _get_enemy_by_type_for_location(player.current_location_id, enemy_type)
        if not enemy:
            enemy = enemies.get_enemy_by_type(enemy_type)
    else:
        enemy = enemies.get_enemy_for_location(player.current_location_id)
        # Бонус aftermath: повышенный шанс встречи с редким/сильным мутантом.
        if is_emission_rare_enemy_bonus():
            loc_enemies = enemies.ENEMIES.get(player.current_location_id, [])
            if loc_enemies:
                enemy = max(loc_enemies, key=lambda e: (e.get("hp", 0), e.get("damage", 0)))

    if not enemy:
        return

    scaled_enemy = _scale_enemy_for_player(
        player,
        enemy,
        player.current_location_id,
        allow_elite=allow_elite,
    )
    limited_mods = get_limited_event_modifiers()
    enemy_stat_mult = max(0.7, float(limited_mods.get("enemy_stat_mult", 1.0) or 1.0))
    if abs(enemy_stat_mult - 1.0) > 0.01:
        scaled_enemy["enemy_hp"] = max(10, int(scaled_enemy["enemy_hp"] * enemy_stat_mult))
        scaled_enemy["enemy_max_hp"] = scaled_enemy["enemy_hp"]
        scaled_enemy["enemy_damage"] = max(1, int(scaled_enemy["enemy_damage"] * enemy_stat_mult))

    initiative = _roll_initiative(player, scaled_enemy["enemy_speed"])

    # Сохраняем состояние боя
    _combat_state[user_id] = {
        'enemy_name': scaled_enemy['enemy_name'],
        'enemy_hp': scaled_enemy['enemy_hp'],
        'enemy_max_hp': scaled_enemy['enemy_max_hp'],
        'enemy_damage': scaled_enemy['enemy_damage'],
        'enemy_description': scaled_enemy['enemy_description'],
        'enemy_level': scaled_enemy['enemy_level'],
        'enemy_role': scaled_enemy['enemy_role'],
        'enemy_role_label': scaled_enemy['enemy_role_label'],
        'enemy_speed': scaled_enemy['enemy_speed'],
        'enemy_evade_chance': scaled_enemy['enemy_evade_chance'],
        'enemy_drain_chance': scaled_enemy['enemy_drain_chance'],
        'enemy_drain_min': scaled_enemy['enemy_drain_min'],
        'enemy_drain_max': scaled_enemy['enemy_drain_max'],
        'enemy_is_elite': scaled_enemy['enemy_is_elite'],
        'reward_mult': scaled_enemy['reward_mult'],
        'initiative_player': initiative['player_total'],
        'initiative_enemy': initiative['enemy_total'],
        'turn': 'player',
        'location_id': player.current_location_id,
    }

    message = (
        f"ОПАСНОСТЬ!\n\n"
        f"Во время исследования ты заметил {scaled_enemy['enemy_name']}!\n\n"
        f"{scaled_enemy['enemy_description']}\n\n"
        f"Уровень врага: {scaled_enemy['enemy_level']} | Роль: {scaled_enemy['enemy_role_label']}\n"
        f"HP: {scaled_enemy['enemy_hp']} | Урон: {scaled_enemy['enemy_damage']}\n\n"
        f"🎲 Инициатива:\n"
        f"Ты: d20({initiative['player_roll']}) → {initiative['player_total']}\n"
        f"Враг: d20({initiative['enemy_roll']}) → {initiative['enemy_total']}\n"
    )

    if not initiative["player_first"]:
        enemy_damage = _combat_state[user_id]['enemy_damage']
        total_defense = int(getattr(player, "total_defense", 0) or 0)
        dodge_chance = int(getattr(player, "dodge_chance", 0) or 0)
        current_hp = int(getattr(player, "health", 100) or 100)
        max_hp = int(getattr(player, "max_health", max(current_hp, 1)) or max(current_hp, 1))
        is_dodged = random.randint(1, 100) <= dodge_chance
        if is_dodged:
            message += "\n⚡ Враг начал первым, но ты уклонился от стартового удара!\n"
        else:
            final_damage, hit_cap = _calculate_incoming_damage(player, enemy_damage, total_defense)
            # Открывающий удар не убивает мгновенно: оставляем минимум 1 HP.
            player.health = max(1, current_hp - final_damage)
            database.update_user_stats(user_id, health=player.health)
            message += (
                "\n⚡ Враг выиграл инициативу и атакует первым!\n"
                f"Получен урон: {final_damage} (защита: {total_defense})\n"
                f"Текущее HP: {player.health}/{max_hp}\n"
            )
            if hit_cap:
                message += "Ранняя осторожность снижает тяжесть первого удара.\n"
    else:
        message += "\n✅ Ты выиграл инициативу и действуешь первым!\n"

    active_limited = get_active_limited_event()
    if active_limited and abs(enemy_stat_mult - 1.0) > 0.01:
        pct = int(round((enemy_stat_mult - 1.0) * 100))
        message += f"\n🌐 Ивент «{active_limited.get('name')}»: параметры врага {pct:+d}%\n"

    message += "\nЧто будешь делать?"

    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Атаковать", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Навыки", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Инвентарь", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Убежать", color=VkKeyboardColor.NEGATIVE)

    vk.messages.send(user_id=user_id, message=message, keyboard=keyboard.get_keyboard(), random_id=0)


def _spawn_item(player, vk, user_id: int):
    """Спавн предмета (с учётом локации)"""
    _combat_state, create_location_keyboard, _, _ = _get_main_imports()
    from game.location_mechanics import get_location_loot_bias, get_location_loot_bias_chance

    if random.randint(1, 100) <= SAWDUST_SOUP_RESEARCH_DROP_CHANCE:
        soup = database.get_item_by_name("Суп с опилками")
        if soup:
            item_weight = soup.get('weight', 0.3)
            current_weight = player.inventory.total_weight
            if current_weight + item_weight <= player.max_weight:
                database.add_item_to_inventory(user_id, soup['name'], 1)
                player.inventory.reload()
                vk.messages.send(
                    user_id=user_id,
                    message=(
                        "Ты обыскал территорию!\n\n"
                        "СТРАННАЯ НАХОДКА!\n\n"
                        f"Найдено: {soup['name']}\n"
                        f"Описание: {soup.get('description', 'Без описания.')}\n"
                        f"Вес: {item_weight}кг"
                    ),
                    keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                    random_id=0
                )
                return

    # Проверяем бонус локации
    bias_items = get_location_loot_bias(player.current_location_id)
    bias_chance = get_location_loot_bias_chance(player.current_location_id)

    lvl = max(1, int(getattr(player, "level", 1) or 1))
    if lvl <= 10:
        categories = ['meds', 'consumables', 'food', 'other', 'weapons', 'armor', 'artifacts']
        weights = [24, 20, 12, 18, 10, 10, 6]
    else:
        categories = ['weapons', 'armor', 'artifacts', 'other', 'meds', 'consumables', 'food']
        weights = [20, 20, 18, 18, 10, 8, 6]
    category = random.choices(categories, weights=weights, k=1)[0]
    items_in_category = database.get_items_by_category(category)
    if category in {"weapons", "rare_weapons"}:
        from game.weapon_progression import get_weapon_required_level
        lvl = max(1, int(getattr(player, "level", 1) or 1))
        allowed_weapons = [
            item for item in items_in_category
            if get_weapon_required_level(item) <= lvl + 3
        ]
        items_in_category = allowed_weapons or items_in_category[:1]

    if not items_in_category:
        vk.messages.send(
            user_id=user_id,
            message="Ты обыскал территорию...\n\nНичего не найдено.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    # Проверяем бонус локации — шанс получить тематический предмет
    found_item = None
    is_rare = random.randint(1, 100) <= player.rare_find_chance

    if bias_items and random.random() < bias_chance:
        # Пытаемся найти предмет из бонусного списка
        for bias_name in bias_items:
            for item in items_in_category:
                if bias_name.lower() in item['name'].lower():
                    found_item = item
                    break
            if found_item:
                break

    # Если не нашли бонусный — выбираем случайно
    if not found_item:
        if is_rare and category in ['weapons', 'armor']:
            items_in_category = sorted(items_in_category, key=lambda x: x.get('price', 0), reverse=True)
            found_item = items_in_category[0] if items_in_category else None
            rarity_text = "РЕДКАЯ НАХОДКА!\n\n"
        else:
            found_item = random.choice(items_in_category)
            rarity_text = ""
    else:
        rarity_text = "🎯 **ТЕМАТИЧЕСКАЯ НАХОДКА!**\n\n"

    if not found_item:
        return

    item_weight = found_item.get('weight', 1.0)
    current_weight = player.inventory.total_weight

    if current_weight + item_weight > player.max_weight:
        message = (
            f"Ты обыскал территорию!\n\n"
            f"Найдено {found_item['name']}, но не можешь взять — не хватает места!\n"
            f"Вес предмета: {item_weight}кг\n"
            f"Твой рюкзак: {current_weight}/{player.max_weight}кг"
        )
    else:
        database.add_item_to_inventory(user_id, found_item['name'], 1)
        player.inventory.reload()

        item_info = f"{found_item['name']}"
        if found_item.get('attack'):
            item_info += f" УРН:{found_item['attack']}"
        if found_item.get('defense'):
            item_info += f" ЗАЩ:{found_item['defense']}"

        message = f"Ты обыскал территорию!\n\n{rarity_text}Найдено: {item_info}\nВес: {item_weight}кг"

    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def create_combat_keyboard(player=None, user_id=None):
    """Клавиатура боя"""
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Атаковать", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Инвентарь", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    # Кнопка навыков - показываем только если есть выбранная специализация.
    if player and player.player_class:
        keyboard.add_button("Навыки", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Убежать", color=VkKeyboardColor.NEGATIVE)
    else:
        keyboard.add_button("Убежать", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_skills_keyboard(player, user_id: int = None):
    """Клавиатура навыков в бою"""
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
    from models.classes import get_class

    keyboard = VkKeyboard(one_time=False)

    class_id = player.player_class
    if not class_id:
        return None

    player_class = get_class(class_id)
    if not player_class:
        return None

    # Получаем кулдауны игрока
    if user_id is None:
        user_id = getattr(player, 'vk_id', None)
    cooldowns = _skill_cooldowns.get(user_id, {})
    active_effects = _active_skill_effects.get(user_id, {})

    # Добавляем кнопки активных навыков
    for skill in player_class.active_skills:
        skill_name = skill["name"]
        skill_cost = skill["energy_cost"]
        cd = cooldowns.get(skill_name, 0)

        # Проверяем, можно ли использовать навык
        can_use = True
        status = ""

        if player.energy < skill_cost:
            can_use = False
            status = f" (мало энергии)"
        elif cd > 0:
            can_use = False
            status = f" (перезарядка {cd} ход)"

        # Проверяем активные эффекты
        for effect_name, effect_turns in active_effects.items():
            if "damage_boost" in str(skill.get("effect", {})) and effect_name == "damage_boost":
                status = f" (активен)"
            elif skill_name == "Уклонение" and effect_name == "perfect_dodge":
                status = f" (активен)"
            elif skill_name == "Бронирование" and effect_name == "temp_defense":
                status = f" (активен)"

        btn_text = f"{skill_name} ({skill_cost} эн)"
        if status:
            btn_text = f"{skill_name}{status}"

        color = VkKeyboardColor.POSITIVE if can_use else VkKeyboardColor.SECONDARY
        keyboard.add_button(btn_text, color=color)
        keyboard.add_line()

    keyboard.add_button("Инвентарь", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def show_skills_in_combat(player, vk, user_id):
    """Показать навыки в бою"""
    from models.classes import get_class

    class_id = player.player_class
    if not class_id:
        vk.messages.send(
            user_id=user_id,
            message="⚡ У тебя нет класса!\n\nСначала получи класс у Наставника в Убежище.",
            random_id=0
        )
        return

    player_class = get_class(class_id)
    if not player_class:
        return

    # Формируем сообщение
    msg = f"⚡НАВЫКИ КЛАССА {class_id.upper()}\n\n"
    msg += f"Твоя энергия: {player.energy}/100\n\n"

    cooldowns = _skill_cooldowns.get(user_id, {})
    active_effects = _active_skill_effects.get(user_id, {})

    for skill in player_class.active_skills:
        skill_name = skill["name"]
        skill_desc = skill["description"]
        skill_cost = skill["energy_cost"]
        cd = cooldowns.get(skill_name, 0)

        # Проверяем активные эффекты
        effect_active = False
        for effect_name in active_effects:
            if "damage_boost" in str(skill.get("effect", {})) and effect_name == "damage_boost":
                effect_active = True

        status = "✅ Готов" if cd == 0 and not effect_active else "⏳"
        if cd > 0:
            status = f"🔄 Перезарядка: {cd} ход"
        elif effect_active:
            status = f"✨ Активен"
        elif player.energy < skill_cost:
            status = f"❌ Мало энергии"

        msg += f"<b>{skill_name}\n"
        msg += f"   {skill_desc}\n"
        msg += f"   Энергия: {skill_cost} | Кулдаун: {skill['cooldown']} ходов\n"
        msg += f"   Статус: {status}\n\n"

    # Показываем активные эффекты
    if active_effects:
        msg += "🔮Активные эффекты:\n"
        for effect_name, turns in active_effects.items():
            msg += f"• {effect_name}: {turns} ходов\n"

    keyboard = create_skills_keyboard(player, user_id)
    if not keyboard:
        return

    vk.messages.send(
        user_id=user_id,
        message=msg,
        keyboard=keyboard.get_keyboard(),
        random_id=0
    )


def use_skill(player, vk, user_id: int, skill_name: str):
    """Использовать навык в бою"""
    from models.classes import get_class
    from infra import database

    combat = _combat_state.get(user_id)
    if not combat:
        vk.messages.send(
            user_id=user_id,
            message="⚠️ Ты не в бою!",
            random_id=0
        )
        return

    class_id = player.player_class
    if not class_id:
        vk.messages.send(
            user_id=user_id,
            message="⚡ У тебя нет класса!",
            random_id=0
        )
        return

    player_class = get_class(class_id)
    if not player_class:
        return

    # Ищем навык
    skill = None
    requested_skill = skill_name.lower().strip()
    for s in player_class.active_skills:
        known_skill = s["name"].lower()
        if requested_skill in known_skill or known_skill in requested_skill:
            skill = s
            break

    if not skill:
        vk.messages.send(
            user_id=user_id,
            message=f"⚡ Навык '{skill_name}' не найден!",
            random_id=0
        )
        return

    # Проверяем кулдаун
    cooldowns = _skill_cooldowns.get(user_id, {})
    if cooldowns.get(skill["name"], 0) > 0:
        vk.messages.send(
            user_id=user_id,
            message=f"⚡ Навык '{skill['name']}' на перезарядке! Осталось {cooldowns[skill['name']]} ходов.",
            random_id=0
        )
        return

    # Проверяем энергию
    if player.energy < skill["energy_cost"]:
        vk.messages.send(
            user_id=user_id,
            message=f"⚡ Не хватает энергии! Нужно {skill['energy_cost']}, есть {player.energy}.",
            random_id=0
        )
        return

    # Тратим энергию
    new_energy = player.energy - skill["energy_cost"]
    database.update_user_stats(user_id, energy=new_energy)
    player.energy = new_energy

    # Устанавливаем кулдаун
    if user_id not in _skill_cooldowns:
        _skill_cooldowns[user_id] = {}
    _skill_cooldowns[user_id][skill["name"]] = skill["cooldown"]

    # Применяем эффект навыка
    effect = skill.get("effect", {})
    result_msg = _apply_skill_effect(player, vk, user_id, skill, combat, effect)

    # === Проверяем, нанесен ли урон (мгновенные эффекты) или требуется следующий ход ===
    instant_damage_effects = ["double_shot", "burst_count", "damage_mult", "ignore_defense", "self_heal"]

    if any(eff in effect for eff in instant_damage_effects):
        # Мгновенный урон - обрабатываем ответ врага
        if combat['enemy_hp'] > 0:
            # Враг атакует
            enemy_damage = combat['enemy_damage']
            if combat.get("enemy_role") == "bruiser":
                hp_ratio = combat['enemy_hp'] / max(1, combat['enemy_max_hp'])
                if hp_ratio <= 0.40:
                    enemy_damage = int(enemy_damage * 1.15)
                    result_msg += "\n😡 Танк в ярости: урон врага усилен!"
            active_effects = get_active_effects(user_id)

            is_dodged = random.randint(1, 100) <= player.dodge_chance
            if is_dodged:
                result_msg += f"\nТы уклонился от атаки!"
            else:
                total_defense = player.total_defense

                # Применяем эффекты защиты
                if "temp_defense_active" in active_effects:
                    total_defense += active_effects.get("temp_defense", 0)
                if "incoming_damage_reduction" in active_effects:
                    enemy_damage = int(enemy_damage * (1 - active_effects["incoming_damage_reduction"]))
                if "enemy_damage_reduction" in active_effects:
                    enemy_damage = int(enemy_damage * (1 - active_effects["enemy_damage_reduction"]))

                final_damage = max(1, enemy_damage - total_defense)
                player.health -= final_damage
                result_msg += f"\n{combat['enemy_name']} атакует!\nПолучен урон: {final_damage}"

                # Роль "Контролёр": дренаж энергии при попадании.
                if combat.get("enemy_role") == "controller":
                    drain_chance = int(combat.get("enemy_drain_chance", 0))
                    if drain_chance > 0 and random.randint(1, 100) <= drain_chance:
                        drain_min = int(combat.get("enemy_drain_min", 6))
                        drain_max = int(combat.get("enemy_drain_max", 12))
                        energy_drain = min(player.energy, random.randint(drain_min, drain_max))
                        if energy_drain > 0:
                            player.energy -= energy_drain
                            result_msg += f"\n🧠 Контролёр высасывает энергию: -{energy_drain}⚡"

                # Проверка на смерть
                if player.health <= 0:
                    player.health = 0
                    database.update_user_stats(user_id, health=0)
                    del _combat_state[user_id]
                    _handle_death(
                        player,
                        vk,
                        user_id,
                        cause=f"Смертельный удар в бою ({combat.get('enemy_name', 'враг')})",
                        killer_name=combat.get('enemy_name'),
                        final_damage=final_damage,
                    )
                    return

        stamina_regen = _restore_energy_from_stamina(player)
        if stamina_regen > 0:
            result_msg += f"\n🔋 Выносливость восстанавливает энергию: +{stamina_regen}⚡"

        # Проверяем победу
        if combat['enemy_hp'] <= 0:
            database.update_user_stats(user_id, energy=player.energy)
            result_msg += _handle_victory(player, combat, user_id, vk=vk)
            from handlers.keyboards import create_resume_keyboard
            vk.messages.send(
                user_id=user_id,
                message=result_msg,
                keyboard=create_resume_keyboard(player.current_location_id, player.level, user_id).get_keyboard(),
                random_id=0
            )
            return

        # Обновляем HP в БД
        database.update_user_stats(user_id, health=player.health, energy=player.energy)

        # Прогресс-бары
        enemy_hp_bar = _create_hp_bar(combat['enemy_hp'], combat['enemy_max_hp'])
        player_hp_bar = _create_hp_bar(player.health, player.max_health)

        result_msg += (
            f"\n\n{combat['enemy_name']}\n"
            f"HP {enemy_hp_bar} {combat['enemy_hp']}/{combat['enemy_max_hp']}\n\n"
            f"Ты\n"
            f"HP {player_hp_bar} {player.health}/{player.max_health}"
        )
    else:
        # Не мгновенный эффект - показываем сообщение и возвращаем в бой
        stamina_regen = _restore_energy_from_stamina(player)
        if stamina_regen > 0:
            result_msg += f"\n🔋 Выносливость восстанавливает энергию: +{stamina_regen}⚡"
        database.update_user_stats(user_id, energy=player.energy)

    # Уменьшаем кулдауны
    _decrease_cooldowns(user_id)

    # Сохраняем состояние боя
    _combat_state[user_id] = combat

    # Показываем результат и клавиатуру боя
    vk.messages.send(
        user_id=user_id,
        message=result_msg,
        keyboard=create_combat_keyboard(player, user_id).get_keyboard(),
        random_id=0
    )


def _apply_skill_effect(player, vk, user_id: int, skill: dict, combat: dict, effect: dict):
    """Применить эффект навыка"""
    skill_name = skill["name"]
    message = ""

    # === Двойной выстрел ===
    if "double_shot" in effect:
        second_mult = effect.get("second_damage_mult", 0.7)

        weapon_damage, _, _ = _resolve_player_weapon(player, user_id=user_id)
        melee = player.melee_damage
        first_damage = weapon_damage + melee
        first_damage, _ = _apply_weapon_damage_bonus(player, first_damage)

        # Второй выстрел
        second_damage = int(first_damage * second_mult)

        total_damage = first_damage + second_damage
        combat['enemy_hp'] -= total_damage

        message = f"🎯{skill_name}\n\n"
        message += f"Первый выстрел: {first_damage} урона\n"
        message += f"Второй выстрел: {second_damage} урона ({int(second_mult*100)}%)\n"
        message += f"<b>Всего: {total_damage} урона\n\n"

    # === Точный выстрел (damage_boost) ===
    elif "damage_boost" in effect:
        mult = effect.get("damage_boost", 1.5)

        if user_id not in _active_skill_effects:
            _active_skill_effects[user_id] = {}
        _active_skill_effects[user_id]["damage_boost"] = 1  # 1 ход
        _active_skill_effects[user_id]["damage_boost_mult"] = mult

        message = f"🎯{skill_name}\n\n"
        message += f"Прицел взят! Следующая атака нанесет {int((mult-1)*100)}% бонусного урона.\n\n"
        message += "Используй 'Атаковать' для нанесения удара!\n\n"

    # === Очередь (burst) ===
    elif "burst_count" in effect:
        burst_count = effect.get("burst_count", 3)
        burst_damage = effect.get("burst_damage", 0.4)

        weapon_damage, _, _ = _resolve_player_weapon(player, user_id=user_id)
        melee = player.melee_damage
        base_damage = weapon_damage + melee
        base_damage, _ = _apply_weapon_damage_bonus(player, base_damage)
        per_shot = int(base_damage * burst_damage)
        total_damage = per_shot * burst_count

        combat['enemy_hp'] -= total_damage

        message = f"🔥{skill_name}\n\n"
        message += f"Очередь из {burst_count} выстрелов:\n"
        for i in range(burst_count):
            message += f"  Выстрел {i+1}: {per_shot} урона\n"
        message += f"<b>Всего: {total_damage} урона\n\n"

    # === Подавление ===
    elif "enemy_damage_reduction" in effect:
        reduction = effect.get("enemy_damage_reduction", 0.25)

        if user_id not in _active_skill_effects:
            _active_skill_effects[user_id] = {}
        _active_skill_effects[user_id]["enemy_damage_reduction"] = 1

        message = f"🛡️{skill_name}\n\n"
        message += f"Враг подавлен! Его атаки наносят на {int(reduction*100)}% меньше урона.\n\n"

    # === Прицельный выстрел ===
    elif "damage_mult" in effect:
        mult = effect.get("damage_mult", 2.5)
        cannot_dodge = effect.get("cannot_dodge", False)

        weapon_damage, _, _ = _resolve_player_weapon(player, user_id=user_id)
        melee = player.melee_damage
        base_damage = weapon_damage + melee
        base_damage, _ = _apply_weapon_damage_bonus(player, base_damage)
        total_damage = int(base_damage * mult)

        combat['enemy_hp'] -= total_damage

        message = f"🎯{skill_name}\n\n"
        message += f"Мощный прицельный выстрел!\n"
        message += f"База: {base_damage} x {mult} = {total_damage} урона\n"
        if cannot_dodge:
            message += "Враг не может уклониться!\n"
        message += "\n"

    # === Незримый ===
    elif "incoming_damage_reduction" in effect:
        reduction = effect.get("incoming_damage_reduction", 0.5)

        if user_id not in _active_skill_effects:
            _active_skill_effects[user_id] = {}
        _active_skill_effects[user_id]["incoming_damage_reduction"] = 1

        message = f"👻{skill_name}\n\n"
        message += f"Ты стал невидимым! Следующий урон врага уменьшен на {int(reduction*100)}%.\n\n"

    # === Шквал огня ===
    elif "burst_count" in effect:  # Уже обработано выше, но для пулемётчика
        burst_count = effect.get("burst_count", 5)
        burst_damage = effect.get("burst_damage", 0.3)

        weapon_damage, _, _ = _resolve_player_weapon(player, user_id=user_id)
        melee = player.melee_damage
        base_damage = weapon_damage + melee
        base_damage, _ = _apply_weapon_damage_bonus(player, base_damage)
        per_shot = int(base_damage * burst_damage)
        total_damage = per_shot * burst_count

        combat['enemy_hp'] -= total_damage

        message = f"💥{skill_name}\n\n"
        message += f"Шквал из {burst_count} выстрелов:\n"
        for i in range(burst_count):
            message += f"  Выстрел {i+1}: {per_shot} урона\n"
        message += f"<b>Всего: {total_damage} урона\n\n"

    # === Бронирование ===
    elif "temp_defense" in effect:
        defense = effect.get("temp_defense", 25)

        if user_id not in _active_skill_effects:
            _active_skill_effects[user_id] = {}
        _active_skill_effects[user_id]["temp_defense"] = defense
        _active_skill_effects[user_id]["temp_defense_active"] = 1

        message = f"🛡️{skill_name}\n\n"
        message += f"Бронирование активировано! +{defense} защиты на 1 ход.\n\n"

    # === Клинок в сердце ===
    elif "ignore_defense" in effect:
        ignore_def = effect.get("ignore_defense", 20)

        weapon_damage, _, _ = _resolve_player_weapon(player, user_id=user_id)
        melee = player.melee_damage
        base_damage = weapon_damage + melee
        base_damage, _ = _apply_weapon_damage_bonus(player, base_damage)
        total_damage = int(base_damage * 1.5)  # 150% урона

        combat['enemy_hp'] -= total_damage

        message = f"🗡️{skill_name}\n\n"
        message += f"Точный удар в уязвимое место!\n"
        message += f"Урон: {total_damage} (150%)\n"
        message += f"Игнорирование защиты: {ignore_def}%\n\n"

    # === Уклонение (perfect_dodge) ===
    elif "perfect_dodge" in effect:
        if user_id not in _active_skill_effects:
            _active_skill_effects[user_id] = {}
        _active_skill_effects[user_id]["perfect_dodge"] = 1

        message = f"💨{skill_name}\n\n"
        message += "Ты готов уклониться от следующей атаки!\n\n"

    # === Полевое лечение ===
    elif "self_heal" in effect:
        heal_value = max(1, int(effect.get("self_heal", 40) or 40))
        passive = player._get_passive_bonuses() if hasattr(player, "_get_passive_bonuses") else {}
        heal_bonus_pct = max(0, int(passive.get("self_heal_bonus_pct", 0) or 0))
        if heal_bonus_pct > 0:
            heal_value = max(1, int(heal_value * (100 + heal_bonus_pct) / 100))
        old_health = int(getattr(player, "health", 0) or 0)
        max_health = int(getattr(player, "max_health", max(old_health, 1)) or max(old_health, 1))
        player.health = min(max_health, old_health + heal_value)
        restored = player.health - old_health

        message = f"🩺{skill_name}\n\n"
        if restored > 0:
            message += f"Раны быстро стянуты полевой перевязкой: HP {old_health} → {player.health}/{max_health}.\n\n"
        else:
            message += "Перевязка готова, но лечить сейчас нечего.\n\n"

    # === Заградительный огонь ===
    elif "aoe_damage_reduction" in effect:
        reduction = effect.get("aoe_damage_reduction", 0.15)

        if user_id not in _active_skill_effects:
            _active_skill_effects[user_id] = {}
        _active_skill_effects[user_id]["aoe_damage_reduction"] = reduction

        message = f"🔥{skill_name}\n\n"
        message += f"Заградительный огонь! Все враги поблизости наносят на {int(reduction*100)}% меньше урона.\n\n"

    else:
        message = f"⚡{skill_name}\n\nНавык активирован!\n\n"

    return message


def _decrease_cooldowns(user_id: int):
    """Уменьшить кулдауны навыков после хода"""
    if user_id not in _skill_cooldowns:
        return

    for skill_name in list(_skill_cooldowns[user_id].keys()):
        _skill_cooldowns[user_id][skill_name] -= 1
        if _skill_cooldowns[user_id][skill_name] <= 0:
            del _skill_cooldowns[user_id][skill_name]

    # Уменьшаем активные эффекты
    if user_id in _active_skill_effects:
        for effect_name in list(_active_skill_effects[user_id].keys()):
            if isinstance(_active_skill_effects[user_id][effect_name], int):
                _active_skill_effects[user_id][effect_name] -= 1
                if _active_skill_effects[user_id][effect_name] <= 0:
                    del _active_skill_effects[user_id][effect_name]
                    if effect_name == "damage_boost":
                        _active_skill_effects[user_id].pop("damage_boost_mult", None)


def get_active_effects(user_id: int) -> dict:
    """Получить активные эффекты игрока"""
    return _active_skill_effects.get(user_id, {})


def _resolve_player_weapon(player, user_id: int | None = None) -> tuple[int, str | None, bool]:
    """Вернуть урон экипированного оружия; если предмета уже нет — снять экипировку."""
    weapon_damage = 0
    weapon_name = None
    weapon_is_knife = False

    equipped_name = getattr(player, "equipped_weapon", None)
    if not equipped_name:
        return weapon_damage, weapon_name, weapon_is_knife

    player.inventory.reload()
    inv_weapon = next((w for w in player.inventory.weapons if w.get("name") == equipped_name), None)
    if not inv_weapon:
        player.equipped_weapon = None
        if user_id is not None:
            database.update_user_stats(user_id, equipped_weapon=None)
        return weapon_damage, weapon_name, weapon_is_knife

    weapon_name = equipped_name
    weapon_damage = int(inv_weapon.get('attack', 0) or 0)
    weapon_lower = weapon_name.lower()
    weapon_is_knife = (
        "knife" in weapon_lower or "machete" in weapon_lower or
        "bayonet" in weapon_lower or "dagger" in weapon_lower or
        "нож" in weapon_lower or "мачете" in weapon_lower
    )
    return weapon_damage, weapon_name, weapon_is_knife


def _apply_weapon_damage_bonus(player, damage: int) -> tuple[int, int]:
    """Применить пассивный модификатор урона оружия класса."""
    passive = player._get_passive_bonuses()
    bonus_pct = int(passive.get('weapon_damage', 0) or 0)
    if bonus_pct == 0:
        return damage, 0
    multiplier = max(0.1, 1 + bonus_pct / 100)
    return max(1, int(damage * multiplier)), bonus_pct


def _apply_crit_damage_bonus(player, damage: int) -> tuple[int, int]:
    """Применить крит-множитель с учётом бонуса крит-урона класса."""
    crit_bonus_pct = int(getattr(player, "crit_damage", 0) or 0)
    crit_mult = 1.5 + (crit_bonus_pct / 100.0)
    return int(damage * crit_mult), crit_bonus_pct


def _restore_energy_from_stamina(player) -> int:
    """
    Восстановление энергии от выносливости за боевой ход.
    Формула мягкая: без заметного бафа на низких уровнях, но полезна в мид/лейт-гейме.
    """
    effective_stamina = int(getattr(player, "effective_stamina", getattr(player, "stamina", 1)) or 1)
    regen = max(0, (effective_stamina - 4) // 4)  # 4->0, 8->1, 12->2, 16->3, 20->4
    if regen <= 0:
        return 0
    old_energy = int(getattr(player, "energy", 0) or 0)
    player.energy = min(100, old_energy + regen)
    return max(0, player.energy - old_energy)


def handle_combat_attack(player, vk, user_id: int):
    """Атаковать врага"""
    _combat_state, create_location_keyboard, _, _ = _get_main_imports()

    combat = _combat_state.get(user_id)
    if not combat:
        return
    
    # === Проверяем активные эффекты ===
    active_effects = get_active_effects(user_id)

    weapon_damage, weapon_name, weapon_is_knife = _resolve_player_weapon(player, user_id=user_id)

    melee = player.melee_damage
    total_damage = weapon_damage + melee
    total_damage, weapon_bonus_pct = _apply_weapon_damage_bonus(player, total_damage)
    
    # === Применяем эффекты навыков ===
    skill_message = ""

    # Damage boost (Точный выстрел)
    if "damage_boost" in active_effects:
        boost_mult = float(active_effects.get("damage_boost_mult", 1.5) or 1.5)
        total_damage = int(total_damage * boost_mult)
        skill_message += f"🎯 Прицельный приём! +{int((boost_mult - 1) * 100)}% урона!\n"
        del _active_skill_effects[user_id]["damage_boost"]
        _active_skill_effects[user_id].pop("damage_boost_mult", None)

    is_crit = random.randint(1, 100) <= player.crit_chance
    if is_crit:
        total_damage, crit_bonus_pct = _apply_crit_damage_bonus(player, total_damage)
    else:
        crit_bonus_pct = 0

    # Роль "Хищник": враг может уклониться от атаки.
    enemy_evaded = False
    evade_chance = int(combat.get("enemy_evade_chance", 0))
    if evade_chance > 0 and random.randint(1, 100) <= evade_chance:
        enemy_evaded = True
        total_damage = 0

    total_damage, mastery_cap = _apply_early_weapon_mastery_cap(player, total_damage, weapon_is_knife)
    combat['enemy_hp'] -= total_damage
    
    # Проверка кровотечения при атаке ножом
    bleed_applied = False
    if weapon_is_knife:
        effective_luck = int(getattr(player, "effective_luck", player.luck) or player.luck)
        bleed_chance = 30 + effective_luck * 2  # 30-50% + удача
        if random.randint(1, 100) <= bleed_chance:
            combat['bleed_turns'] = combat.get('bleed_turns', 0) + 3  # 3 хода кровотечения
            bleed_applied = True

    # Урон от кровотечения (если есть)
    bleed_damage = 0
    if combat.get('bleed_turns', 0) > 0:
        effective_luck = int(getattr(player, "effective_luck", player.luck) or player.luck)
        bleed_damage = 5 + effective_luck  # 5-10 урона от кровотечения
        combat['enemy_hp'] -= bleed_damage
        combat['bleed_turns'] -= 1

    # Формируем сообщение об уроне
    damage_details = []
    if weapon_damage > 0:
        damage_details.append(f"Оружие {weapon_name}: {weapon_damage}")
    damage_details.append(f"Рукопашный: {melee}")
    if weapon_bonus_pct:
        sign = "+" if weapon_bonus_pct > 0 else ""
        damage_details.append(f"Модификатор класса: {sign}{weapon_bonus_pct}%")
    if mastery_cap:
        damage_details.append(f"Контроль оружия до L{EARLY_WEAPON_MASTERY_CAP_LEVEL}: потолок {mastery_cap}")

    # Добавляем информацию о характеристиках
    crit_chance = player.crit_chance
    dodge_chance = player.dodge_chance
    total_defense = player.total_defense

    message = f"⚔️ТЫ АТАКУЕШЬ {combat['enemy_name'].upper()}\n\n"
    message += f"🎯 Шанс крита: {crit_chance}% | 💨 Уклонение: {dodge_chance}%\n"
    message += f"🛡️ Твоя защита: {total_defense}\n"
    if combat.get("enemy_level"):
        message += f"👹 Враг L{combat['enemy_level']} ({combat.get('enemy_role_label', 'Неизвестно')})\n"

    if enemy_evaded:
        message += "\n💨 Враг резко сместился и уклонился от удара!\n"
    elif is_crit:
        crit_msg = "🔥КРИТИЧЕСКИЙ УДАР! x1.5"
        if crit_bonus_pct > 0:
            crit_msg += f" +{crit_bonus_pct}%"
        message += f"\n{crit_msg}\n"
    message += f"Нанесён урон: {total_damage}\n"
    message += f"({(' | '.join(damage_details))})\n"

    # Сообщение о кровотечении
    if bleed_applied:
        message += f"\n🩸КРОВОТЕЧЕНИЕ! Враг истекает кровью!\n"
    if bleed_damage > 0:
        message += f"🩸 Кровотечение наносит {bleed_damage} урона!\n"

    # Восстановление энергии от выносливости в конце своего действия.
    stamina_regen = _restore_energy_from_stamina(player)
    if stamina_regen > 0:
        message += f"\n🔋 Выносливость восстанавливает энергию: +{stamina_regen}⚡\n"

    # Определяем какую клавиатуру показывать
    keyboard = None

    if combat['enemy_hp'] <= 0:
        database.update_user_stats(user_id, energy=player.energy)
        message += _handle_victory(player, combat, user_id, vk=vk)
        from handlers.keyboards import create_resume_keyboard
        keyboard = create_resume_keyboard(player.current_location_id, player.level, user_id)
    else:
        enemy_damage = combat['enemy_damage']
        if combat.get("enemy_role") == "bruiser":
            hp_ratio = combat['enemy_hp'] / max(1, combat['enemy_max_hp'])
            if hp_ratio <= 0.40:
                enemy_damage = int(enemy_damage * 1.15)
                message += "\n😡 Танк в ярости: урон врага усилен!\n"
        
        # === Проверяем perfect_dodge (навык Уклонение) ===
        if "perfect_dodge" in active_effects:
            message += "\n💨УКЛОНЕНИЕ! (навык Уклонение)\n"
            del _active_skill_effects[user_id]["perfect_dodge"]
        else:
            is_dodged = random.randint(1, 100) <= player.dodge_chance
            if is_dodged:
                message += f"\n💨УКЛОНЕНИЕ! (шанс: {player.dodge_chance}%)\n"
            else:
                total_defense = player.total_defense

                # === Применяем temp_defense (Бронирование) ===
                if "temp_defense_active" in active_effects:
                    temp_def = active_effects.get("temp_defense", 0)
                    total_defense += temp_def
                    message += f"🛡️БРОНИРОВАНИЕ: +{temp_def} защиты!\n"

                # === Применяем incoming_damage_reduction (Незримый) ===
                if "incoming_damage_reduction" in active_effects:
                    reduction = active_effects["incoming_damage_reduction"]
                    enemy_damage = int(enemy_damage * (1 - reduction))
                    message += f"👻НЕЗРИМЫЙ: урон уменьшен на {int(reduction*100)}%!\n"
                    del _active_skill_effects[user_id]["incoming_damage_reduction"]

                # === Применяем enemy_damage_reduction (Подавление) ===
                if "enemy_damage_reduction" in active_effects:
                    reduction = active_effects["enemy_damage_reduction"]
                    enemy_damage = int(enemy_damage * (1 - reduction))
                    message += f"🔥ПОДАВЛЕНИЕ: враг ослаблен на {int(reduction*100)}%!\n"
                    del _active_skill_effects[user_id]["enemy_damage_reduction"]

                final_damage, hit_cap = _calculate_incoming_damage(player, enemy_damage, total_defense)
                player.health -= final_damage
                message += f"\n⚔️{combat['enemy_name']} АТАКУЕТ!\n"
                message += f"Урон врага: {enemy_damage} → Получено:{final_damage} (защита: {total_defense})\n"
                if hit_cap:
                    message += "Ранняя осторожность снижает тяжесть удара.\n"

                # Роль "Контролёр": дренаж энергии при попадании.
                if combat.get("enemy_role") == "controller":
                    drain_chance = int(combat.get("enemy_drain_chance", 0))
                    if drain_chance > 0 and random.randint(1, 100) <= drain_chance:
                        drain_min = int(combat.get("enemy_drain_min", 6))
                        drain_max = int(combat.get("enemy_drain_max", 12))
                        energy_drain = min(player.energy, random.randint(drain_min, drain_max))
                        if energy_drain > 0:
                            player.energy -= energy_drain
                            message += f"🧠 Контролёр высасывает энергию: -{energy_drain}⚡\n"

            # Проверка на смерть
            if player.health <= 0:
                player.health = 0
                database.update_user_stats(user_id, health=0)
                del _combat_state[user_id]
                _handle_death(
                    player,
                    vk,
                    user_id,
                    cause=f"Смертельный контрудар ({combat.get('enemy_name', 'враг')})",
                    killer_name=combat.get('enemy_name'),
                    final_damage=final_damage,
                )
                return

            database.update_user_stats(user_id, health=player.health, energy=player.energy)

        # Показываем состояние кровотечения
        if combat.get('bleed_turns', 0) > 0:
            message += f"\n🩸 Кровотечение врага: {combat['bleed_turns']} ходов"

        message += f"\n\n{_format_combat_hud(combat, player)}"

        # Уменьшаем кулдауны после хода
        _decrease_cooldowns(user_id)

        # Показываем активные эффекты
        active_effects = get_active_effects(user_id)
        if active_effects:
            effects_msg = "\n🔮АКТИВНЫЕ ЭФФЕКТЫ:\n"
            for eff_name, eff_val in active_effects.items():
                if isinstance(eff_val, int) and eff_val > 0:
                    effects_msg += f"• {eff_name}: {eff_val} ход\n"
            message += effects_msg

        # Показываем кулдауны навыков
        cooldowns = _skill_cooldowns.get(user_id, {})
        if cooldowns:
            cd_msg = "\n⏳ПЕРЕЗАРЯДКА НАВЫКОВ:\n"
            for skill_name, cd_val in cooldowns.items():
                cd_msg += f"• {skill_name}: {cd_val} ход\n"
            message += cd_msg

        # Сохраняем состояние боя и показываем клавиатуру боя
        _combat_state[user_id] = combat
        keyboard = create_combat_keyboard(player, user_id)

    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=keyboard.get_keyboard(),
        random_id=0
    )


def handle_combat_flee(player, vk, user_id: int):
    """Попытаться убежать"""
    _combat_state, create_location_keyboard, _, _ = _get_main_imports()

    combat = _combat_state.get(user_id)
    if not combat:
        return

    passive = player._get_passive_bonuses() if hasattr(player, "_get_passive_bonuses") else {}
    flee_chance = max(5, min(90, 50 + int(passive.get("flee_chance_bonus", 0) or 0)))
    if random.randint(1, 100) <= flee_chance:
        del _combat_state[user_id]
        from handlers.keyboards import create_resume_keyboard
        player_hp_bar = _create_hp_bar(player.health, player.max_health, bar_length=14)
        vk.messages.send(
            user_id=user_id,
            message=(
                "Удалось оторваться от противника.\n\n"
                f"{ui.section('Состояние')}\n"
                f"HP      {player_hp_bar} {player.health}/{player.max_health} ({ui.pct(player.health, player.max_health)}%)\n"
                f"Энергия {ui.bar(player.energy, 100, width=14)} {player.energy}/100"
            ),
            keyboard=create_resume_keyboard(player.current_location_id, player.level, user_id).get_keyboard(),
            random_id=0
        )
    else:
        enemy_damage = combat['enemy_damage']
        total_defense = player.total_defense
        final_damage = max(1, enemy_damage - total_defense)
        player.health -= final_damage

        # Проверка на смерть
        if player.health <= 0:
            player.health = 0
            database.update_user_stats(user_id, health=0)
            del _combat_state[user_id]
            _handle_death(
                player,
                vk,
                user_id,
                cause=f"Погиб при попытке отступления ({combat.get('enemy_name', 'враг')})",
                killer_name=combat.get('enemy_name'),
                final_damage=final_damage,
            )
            return

        database.update_user_stats(user_id, health=player.health)
        
        player_hp_bar = _create_hp_bar(player.health, player.max_health, bar_length=14)

        vk.messages.send(
            user_id=user_id,
            message=(
                "Сбежать не получилось.\n\n"
                f"{combat['enemy_name']} атакует!\n"
                f"Урон: {final_damage} (защита: {total_defense})\n\n"
                f"{ui.section('Состояние')}\n"
                f"HP      {player_hp_bar} {player.health}/{player.max_health} ({ui.pct(player.health, player.max_health)}%)"
            ),
            keyboard=create_combat_keyboard(player, user_id).get_keyboard(),
            random_id=0
        )

def _handle_victory(player, combat, user_id: int, vk=None) -> str:
    """Обработка победы над врагом"""
    _combat_state, _, _, _ = _get_main_imports()
    from handlers.quests import track_quest_kill, track_quest_shells
    from game.limited_events import get_limited_event_modifiers, get_active_limited_event

    del _combat_state[user_id]

    reward_mult = max(1.0, float(combat.get("reward_mult", 1.0)))
    limited_mods = get_limited_event_modifiers()
    event_reward_mult = max(0.5, float(limited_mods.get("combat_reward_mult", 1.0) or 1.0))
    reward_mult *= event_reward_mult
    base_xp = _scale_xp_reward(
        random.randint(10, 30),
        player,
        source="combat",
        enemy_level=int(combat.get("enemy_level", 1) or 1),
    )
    experience = max(5, int(base_xp * reward_mult))
    money = max(3, int(random.randint(5, 25) * reward_mult))
    shells_drop = max(1, int(round(random.randint(1, 3) * min(2.0, 0.8 + reward_mult * 0.4))))

    gained_xp = int(player.add_experience(experience))
    player.money += money
    
    # Добавляем гильзы с учетом вместимости мешочка
    shells_info = database.get_shells_info(user_id)
    shells_before = database.get_user_shells(user_id)
    success, msg = database.add_shells(user_id, shells_drop)
    current_shells = database.get_user_shells(user_id)
    capacity = shells_info['capacity']

    # Автопрогресс daily-заданий: убийства и собранные гильзы.
    track_quest_kill(user_id, combat.get("location_id"), vk=vk)
    added_shells = max(0, int(current_shells or 0) - int(shells_before or 0))
    if added_shells > 0:
        track_quest_shells(user_id, count=added_shells, vk=vk)

    database.update_user_stats(user_id, money=player.money)
    
    level_up = getattr(player, "_last_level_up_message", None)
    
    player_hp_bar = _create_hp_bar(player.health, player.max_health, bar_length=14)

    message = (
        f"{ui.title('Победа')}\n"
        f"Ты победил {combat['enemy_name']}.\n\n"
        f"{ui.section('Награда')}\n"
        f"💰 Деньги: +{money} руб.\n"
        f"⭐ Опыт: +{gained_xp}\n"
        f"🎯 Гильзы: {current_shells}/{capacity}\n"
    )
    if reward_mult > 1.0:
        message += f"⚖️ Множитель сложности: x{reward_mult:.2f}\n"
    active_limited = get_active_limited_event()
    if active_limited and abs(event_reward_mult - 1.0) > 0.01:
        message += f"🌐 Ивент «{active_limited.get('name')}»: награда x{event_reward_mult:.2f}\n"

    if not success:
        message += f"⚠️ Мешочек переполнен! {msg}\n"

    lvl = max(1, int(getattr(player, "level", 1) or 1))
    hp_ratio = int(getattr(player, "health", 0) or 0) / max(1, int(getattr(player, "max_health", 100) or 100))
    if lvl <= 12 and hp_ratio <= 0.80 and random.randint(1, 100) <= 35:
        field_supply = random.choice(["Бинт", "Лечебная трава"])
        database.add_item_to_inventory(user_id, field_supply, 1)
        try:
            player.inventory.reload()
        except Exception:
            pass
        message += f"🧰 После боя найдено: {field_supply} x1\n"

    message += (
        f"\n{ui.section('Состояние')}\n"
        f"HP      {player_hp_bar} {player.health}/{player.max_health} ({ui.pct(player.health, player.max_health)}%)\n"
        f"Энергия {ui.bar(player.energy, 100, width=14)} {player.energy}/100\n"
    )

    if level_up:
        message += f"\n{level_up}"
    
    return message
