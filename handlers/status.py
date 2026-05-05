"""Вкладочный экран статуса персонажа."""
from __future__ import annotations

from game import ui
from game.stat_balance import (
    luck_outcome_bonus,
    next_stamina_energy_regen_breakpoint,
    next_stamina_max_energy_breakpoint,
    stamina_energy_regen,
    stamina_max_energy_bonus,
)
from handlers.keyboards import create_status_keyboard
from infra import config as game_config
from infra import database
from infra.state_manager import get_ui_current_screen, set_ui_screen, try_edit_or_send_ui
from models.player import (
    UNSPENT_STAT_POINTS_FLAG,
    calculate_player_max_health,
    format_radiation_rate,
    get_level_xp_required,
    get_radiation_stage,
    normalize_level_experience,
)


STATUS_PAGES = ("Общее", "Прогресс", "Характеристики", "Снаряжение", "Бонусы")


def _refresh_player(player, user_id: int):
    player.inventory.reload()
    user_data = database.get_user_by_vk(user_id)
    if not user_data:
        return {}

    player.level = user_data.get("level", player.level)
    raw_experience = user_data.get("experience", player.experience)
    player.experience = normalize_level_experience(player.level, raw_experience, player.LEVELS, player.MAX_LEVEL)
    if player.experience != int(raw_experience or 0):
        database.update_user_stats(user_id, experience=player.experience)
    player.health = user_data.get("health", player.health)
    player.energy = user_data.get("energy", player.energy)
    player.radiation = user_data.get("radiation", player.radiation)
    player.money = user_data.get("money", player.money)
    player.equipped_armor = user_data.get("equipped_armor")
    player.equipped_weapon = user_data.get("equipped_weapon")
    player.equipped_backpack = user_data.get("equipped_backpack")
    player.equipped_device = user_data.get("equipped_device")
    return user_data


def _armor_lines(user_data: dict | None) -> tuple[list[str], int]:
    slot_icons = {
        "equipped_armor_head": "Голова",
        "equipped_armor_body": "Тело",
        "equipped_armor_legs": "Ноги",
        "equipped_armor_hands": "Руки",
        "equipped_armor_feet": "Обувь",
    }
    lines = []
    total = 0
    for slot, label in slot_icons.items():
        item_name = (user_data or {}).get(slot)
        if not item_name:
            continue
        item = database.get_item_by_name(item_name)
        defense = int((item or {}).get("defense", 0) or 0)
        total += defense
        lines.append(f"{label}: {item_name} (+{defense})")
    return lines, total


def _bonus_parts(passive_bonuses: dict) -> list[str]:
    labels = {
        "dodge": "уклон",
        "crit_chance": "крит",
        "sell_bonus": "продажа",
        "weapon_damage": "урон",
        "knife_damage": "ножи",
        "max_weight": "вес",
        "defense": "защита",
        "strength": "сила",
        "stamina": "выносливость",
        "perception": "восприятие",
        "luck": "удача",
        "rare_find_chance": "редкое",
        "find_chance": "находка",
        "crit_damage": "крит. урон",
        "travel_time_reduction_pct": "путь",
        "travel_event_avoid_chance": "событие в пути",
        "travel_scout_cooldown_reduction": "осмотр",
        "travel_acceleration_energy_reduction": "ускорение",
        "hospital_price_discount_pct": "больница",
        "research_energy_discount_pct": "исследование",
        "radiation_reduction_pct": "радиация",
        "anomaly_bypass_chance": "обход аномалии",
        "artifact_extract_bonus_pct": "добыча арта",
        "precise_anomaly_shell_discount": "точный бросок",
        "self_heal_bonus_pct": "полевое лечение",
        "flee_chance_bonus": "побег",
    }
    percent_stats = {
        "dodge",
        "crit_chance",
        "sell_bonus",
        "weapon_damage",
        "knife_damage",
        "find_chance",
        "rare_find_chance",
        "crit_damage",
        "travel_time_reduction_pct",
        "travel_event_avoid_chance",
        "hospital_price_discount_pct",
        "research_energy_discount_pct",
        "radiation_reduction_pct",
        "anomaly_bypass_chance",
        "artifact_extract_bonus_pct",
        "self_heal_bonus_pct",
        "flee_chance_bonus",
    }
    result = []
    for key, value in passive_bonuses.items():
        if not value:
            continue
        label = labels.get(key, key)
        if key in {"travel_time_reduction_pct", "hospital_price_discount_pct", "radiation_reduction_pct"}:
            result.append(f"{label} -{value}%")
        elif key == "travel_scout_cooldown_reduction":
            result.append(f"{label} -{value}с")
        elif key == "travel_acceleration_energy_reduction":
            result.append(f"{label} -{value} энергии")
        elif key == "precise_anomaly_shell_discount":
            result.append(f"{label} -{value} гильза")
        elif key in percent_stats:
            result.append(f"{label} +{value}%")
        elif key == "max_weight":
            result.append(f"{label} +{value}кг")
        else:
            result.append(f"{label} +{value}")
    return result


def _status_context(player, user_id: int) -> dict:
    user_data = _refresh_player(player, user_id)
    location = player.location
    exp_needed = get_level_xp_required(player.level, player.LEVELS, player.MAX_LEVEL)
    exp_progress = normalize_level_experience(player.level, player.experience, player.LEVELS, player.MAX_LEVEL)
    if player._is_rank_xp_locked() and player.level < player.MAX_LEVEL:
        exp_progress = exp_needed

    weapon_item = None
    if player.equipped_weapon:
        weapon_item = next((w for w in player.inventory.weapons if w.get("name") == player.equipped_weapon), None)
    armor_lines, armor_total = _armor_lines(user_data)
    shells = database.get_shells_info(user_id)
    passive_bonuses = player._get_passive_bonuses()
    current_weight = player.inventory.total_weight
    weight_status = "в норме" if current_weight <= player.max_weight else "перегруз"

    return {
        "location_name": location.name if location else "—",
        "rank_name": player.get_rank_name(),
        "rank_block": player.get_rank_progress_block(),
        "class_name": player.player_class or "нет класса",
        "exp_needed": exp_needed,
        "exp_progress": exp_progress,
        "current_weight": current_weight,
        "weight_status": weight_status,
        "weapon": weapon_item,
        "weapon_attack": int((weapon_item or {}).get("attack", 0) or 0),
        "armor_lines": armor_lines,
        "armor_total": armor_total,
        "artifacts": list(player.equipped_artifacts),
        "backpack": player.equipped_backpack or "—",
        "detector": player.equipped_device or "—",
        "shells": shells,
        "passive_bonuses": passive_bonuses,
        "bonus_parts": _bonus_parts(passive_bonuses),
        "unspent_points": int(database.get_user_flag(user_id, UNSPENT_STAT_POINTS_FLAG, 0) or 0),
    }


def _header(player, ctx: dict, page: int) -> list[str]:
    title = STATUS_PAGES[page]
    return [
        ui.title(f"Статус: {title}"),
        f"Вкладка {page + 1}/{len(STATUS_PAGES)}",
        f"Ур. {player.level} | {ctx['rank_name']} | {ctx['class_name']}",
        "",
    ]


def _overview_page(player, ctx: dict) -> list[str]:
    shells = ctx["shells"]
    lines = _header(player, ctx, 0)
    lines.extend([
        ui.section("Общее"),
        f"Локация: {ctx['location_name']}",
        f"HP: {player.health}/{player.max_health} | Энергия: {player.energy}/{player.max_energy}",
        f"Радиация: {int(player.radiation)} ({format_radiation_rate(player.radiation)})",
        f"Опыт: {ctx['exp_progress']}/{ctx['exp_needed']} | Деньги: {player.money:,} руб.",
        "",
        ui.section("Боеготовность"),
        f"Оружие: {player.equipped_weapon or '—'} | ATK {ctx['weapon_attack']}",
        f"Броня: {ctx['armor_total']} | Артефакты: {len(ctx['artifacts'])}/{player.artifact_slots}",
        f"Вес: {ctx['current_weight']:.1f}/{player.max_weight} кг ({ctx['weight_status']})",
        f"Гильзы: {shells['current']}/{shells['capacity']}",
    ])
    return lines


def _progress_page(player, ctx: dict) -> list[str]:
    rad_stage = get_radiation_stage(player.radiation)
    lines = _header(player, ctx, 1)
    lines.extend([
        ui.section("Показатели"),
        ui.meter_line("HP", player.health, player.max_health, width=14),
        ui.meter_line("Энергия", player.energy, player.max_energy, width=14),
        f"Радфон: {int(player.radiation)} ед. ({format_radiation_rate(player.radiation)})",
        f"Стадия: {rad_stage['name']}",
        rad_stage["note"],
        "",
        ui.section("Прогресс"),
        ui.meter_line("Опыт", min(ctx["exp_progress"], ctx["exp_needed"]), ctx["exp_needed"], width=14),
        f"Деньги: {player.money:,} руб.",
        "",
        ui.section("Ранг"),
        ctx["rank_block"],
    ])
    return lines


def _stats_page(player, ctx: dict) -> list[str]:
    strength_damage = player.effective_strength * max(0, int(getattr(game_config, "STRENGTH_DAMAGE_PER_LEVEL", 2) or 2))
    energy_regen = stamina_energy_regen(player.effective_stamina)
    energy_max_bonus = stamina_max_energy_bonus(player.effective_stamina)
    luck_outcome = luck_outcome_bonus(player.effective_luck)
    base_hp = calculate_player_max_health(player.level, player.effective_stamina, 0)
    next_regen = next_stamina_energy_regen_breakpoint(player.effective_stamina)
    next_max_energy = next_stamina_max_energy_breakpoint(player.effective_stamina)
    lines = _header(player, ctx, 2)
    lines.append(ui.section("Базовые"))
    if ctx["unspent_points"] > 0:
        lines.append(f"Свободные очки: {ctx['unspent_points']}")
    lines.extend([
        f"Сила: {player.effective_strength} (+{strength_damage} урона)",
        f"Выносливость: {player.effective_stamina}",
        f"Восприятие: {player.effective_perception}",
        f"Удача: {player.effective_luck} (+{luck_outcome}% к исходам)",
        "",
        ui.section("Производные"),
        f"Макс. HP: {base_hp}" + (f" + {player.max_health_bonus} от артефактов" if player.max_health_bonus else ""),
        f"Урон: {player.melee_damage} | Броня: {player.total_defense}",
        f"Крит: {player.crit_chance}% | Крит. урон: +{player.crit_damage}%",
        f"Уклонение: {player.dodge_chance}% | Сопротивление: {player.damage_resist}%",
        f"Находки: {player.find_chance}% | Редкое: {player.rare_find_chance}%",
        "",
        ui.section("Энергия"),
        f"Реген в бою: +{energy_regen}/ход" + (f" (след. +{next_regen[1]} с {next_regen[0]} вын.)" if next_regen else ""),
        f"Макс. энергия от выносливости: +{energy_max_bonus}" + (f" (след. +{next_max_energy[1]} с {next_max_energy[0]} вын.)" if next_max_energy else ""),
    ])
    return lines


def _equipment_page(player, ctx: dict) -> list[str]:
    weapon = ctx["weapon"] or {}
    lines = _header(player, ctx, 3)
    lines.extend([
        ui.section("Оружие"),
        f"{player.equipped_weapon or '—'} | ATK {ctx['weapon_attack']}",
    ])
    if weapon:
        lines.append(f"L{weapon.get('item_level', 1)}/{weapon.get('weapon_cap', weapon.get('required_level', 1))} | Прорыв {weapon.get('weapon_ascension', 0)}/10 | Ранг {weapon.get('item_rank', 'common')}")
        if weapon.get("event_bonus_text"):
            lines.append(f"{weapon.get('event_bonus_name')}: {weapon.get('event_bonus_text')}")
    lines.extend(["", ui.section("Броня")])
    if ctx["armor_lines"]:
        lines.extend(ctx["armor_lines"])
        lines.append(f"Всего брони: {ctx['armor_total']}")
    else:
        lines.append("Броня не надета.")
    lines.extend(["", ui.section("Артефакты")])
    if ctx["artifacts"]:
        for name in ctx["artifacts"]:
            lines.append(f"• {name}")
    else:
        lines.append(f"0/{player.artifact_slots}")
    lines.extend(["", ui.section("Снаряжение")])
    lines.append(f"Рюкзак: {ctx['backpack']}")
    lines.append(f"Детектор: {ctx['detector']}")
    return lines


def _bonuses_page(player, ctx: dict) -> list[str]:
    shells = ctx["shells"]
    lines = _header(player, ctx, 4)
    lines.extend([
        ui.section("Груз и боезапас"),
        f"Вес: {ctx['current_weight']:.1f}/{player.max_weight} кг ({ctx['weight_status']})",
        f"Гильзы: {shells['current']}/{shells['capacity']} ({shells['equipped_bag'] or 'мешочек не надет'})",
        "",
        ui.section("Класс"),
    ])
    if player.player_class and ctx["bonus_parts"]:
        lines.append(f"{player.player_class}:")
        for part in ctx["bonus_parts"]:
            lines.append(f"• {part}")
    elif player.player_class:
        lines.append(f"{player.player_class}: активных пассивных бонусов нет.")
    else:
        lines.append("Класс не выбран.")
    return lines


def format_status_page(player, user_id: int, page: int = 0) -> str:
    safe_page = max(0, min(len(STATUS_PAGES) - 1, int(page or 0)))
    ctx = _status_context(player, user_id)
    builders = (_overview_page, _progress_page, _stats_page, _equipment_page, _bonuses_page)
    return "\n".join(builders[safe_page](player, ctx))


def show_status_page(player, vk, user_id: int, page: int = 0):
    safe_page = max(0, min(len(STATUS_PAGES) - 1, int(page or 0)))
    current_ui = get_ui_current_screen(user_id)
    push_current = current_ui.get("name") != "status"
    set_ui_screen(user_id, {"name": "status", "page": safe_page}, push_current=push_current)
    try_edit_or_send_ui(
        vk,
        user_id,
        "status",
        format_status_page(player, user_id, safe_page),
        keyboard=create_status_keyboard(safe_page, len(STATUS_PAGES)).get_keyboard(),
    )


def handle_status_callback(player, vk, user_id: int, payload: dict) -> bool:
    if payload.get("command") != "status_page":
        return False
    show_status_page(player, vk, user_id, int(payload.get("page", 0) or 0))
    return True
