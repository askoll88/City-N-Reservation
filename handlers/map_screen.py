"""
Player map screen.

The map is a route planner, not a teleport list. It exposes regions first and
then gives one practical next step through the current route tree.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from game.constants import RESEARCH_LOCATIONS
from game.map_access import AccessResult, can_enter_location
from game.map_schema import get_map_location, get_locations_by_region
from handlers.keyboards import create_inventory_keyboard, create_map_overview_keyboard, create_map_region_keyboard
from infra.state_manager import get_ui_current_screen, set_ui_screen


@dataclass(frozen=True)
class MapRegion:
    id: str
    label: str
    location_ids: tuple[str, ...]
    route_target: str
    description: str


MAP_REGIONS: dict[str, MapRegion] = {
    "city": MapRegion(
        id="city",
        label="Город",
        location_ids=("город", "больница", "убежище", "черный рынок"),
        route_target="город",
        description="Безопасная база: лечение, убежище, торговля и подготовка.",
    ),
    "military": MapRegion(
        id="military",
        label="Военный сектор",
        location_ids=("дорога_военная_часть", "военная_часть"),
        route_target="дорога_военная_часть",
        description="Боевой сектор через КПП. Дорога ведет к внутреннему периметру военной части.",
    ),
    "science": MapRegion(
        id="science",
        label="НИИ",
        location_ids=("дорога_нии", "главный_корпус_нии"),
        route_target="дорога_нии",
        description="Научная ветка через КПП. Дорога ведет к главному корпусу НИИ.",
    ),
    "forest": MapRegion(
        id="forest",
        label="Лес",
        location_ids=("дорога_зараженный_лес", "зараженный_лес"),
        route_target="дорога_зараженный_лес",
        description="Дикая ветка через КПП. Тропа ведет в зараженную чащу.",
    ),
}

REGION_ALIASES = {
    "город": "city",
    "city": "city",
    "военный": "military",
    "военка": "military",
    "военная": "military",
    "военный сектор": "military",
    "сектор": "military",
    "нии": "science",
    "наука": "science",
    "science": "science",
    "лес": "forest",
    "зараженный лес": "forest",
    "заражённый лес": "forest",
    "forest": "forest",
}

REGION_ORDER = ("city", "military", "science", "forest")
CITY_SERVICE_LOCATIONS = {"больница", "убежище", "черный рынок"}
INNER_TO_ROAD_LOCATION = {
    "военная_часть": "Дорога на военную часть",
    "главный_корпус_нии": "Дорога на НИИ",
    "зараженный_лес": "Дорога на зараженный лес",
}

DANGER_LABELS = {
    "safe": "безопасно",
    "low": "низкая",
    "medium": "средняя",
    "high": "высокая",
    "extreme": "крайняя",
}

LOOT_PROFILE_LABELS = {
    None: "сервисы",
    "military": "оружие, броня, патроны",
    "scientific": "медикаменты, детекторы, артефакты",
    "organic": "органика мутантов, артефакты, ресурсы",
}

LOCATION_COMMAND_LABELS = {
    "город": "Город",
    "кпп": "КПП",
    "больница": "Больница",
    "убежище": "Убежище",
    "черный рынок": "Черный рынок",
    "дорога_военная_часть": "Дорога на военную часть",
    "военная_часть": "Военная часть",
    "дорога_нии": "Дорога на НИИ",
    "главный_корпус_нии": "Главный корпус НИИ",
    "дорога_зараженный_лес": "Дорога на зараженный лес",
    "зараженный_лес": "Зараженный лес",
}


def _current_location_id(player) -> str:
    return str(getattr(player, "current_location_id", "") or "город")


def _location_name(location_id: str) -> str:
    record = get_map_location(location_id)
    return str(record.get("name") or location_id) if record else location_id


def _level_text(record: dict[str, Any]) -> str:
    level_min = int(record.get("level_min", 1) or 1)
    level_max = int(record.get("level_max", level_min) or level_min)
    return str(level_min) if level_min == level_max else f"{level_min}-{level_max}"


def _access_label(access: AccessResult) -> str:
    if access.allowed:
        return "открыто"
    return "закрыто: " + "; ".join(access.reasons[:2])


def _format_active_events(location_id: str) -> str:
    parts: list[str] = []

    try:
        from game.location_mechanics import get_location_modifier, get_zone_mutation_state

        modifier = get_location_modifier(location_id)
        if modifier:
            danger = int(round((float(modifier.get("danger_mult", 1.0) or 1.0) - 1.0) * 100))
            finds = int(round((float(modifier.get("find_chance_mult", 1.0) or 1.0) - 1.0) * 100))
            radiation = int(round((float(modifier.get("radiation_mult", 1.0) or 1.0) - 1.0) * 100))
            mod_bits = []
            if danger:
                mod_bits.append(f"опасность {danger:+d}%")
            if finds:
                mod_bits.append(f"находки {finds:+d}%")
            if radiation:
                mod_bits.append(f"радиация {radiation:+d}%")
            if mod_bits:
                parts.append(", ".join(mod_bits))

        mutation = get_zone_mutation_state(location_id)
        if mutation.get("active"):
            bonus = int(round(float(mutation.get("bonus_find", 0) or 0) * 100))
            parts.append(f"мутация Зоны, находки +{bonus}%")
    except Exception:
        pass

    try:
        from game.limited_events import get_active_limited_event

        limited = get_active_limited_event()
        if limited:
            mins_left = max(0, int(limited.get("seconds_left", 0) or 0) // 60)
            parts.append(f"ивент: {limited.get('name', 'Событие Зоны')} ~{mins_left} мин")
    except Exception:
        pass

    return "; ".join(parts) if parts else "нет активных"


def format_location_map_line(player, location_id: str) -> str:
    record = get_map_location(location_id)
    if not record:
        return f"• {location_id}: нет в карте"

    access = can_enter_location(player, location_id)
    danger = DANGER_LABELS.get(record.get("danger"), str(record.get("danger") or "неизвестно"))
    loot = LOOT_PROFILE_LABELS.get(record.get("loot_profile"), str(record.get("loot_profile") or "смешанный лут"))
    try:
        from game.location_mechanics import format_region_loop_status

        loop_status = format_region_loop_status(getattr(player, "user_id", None), location_id)
    except Exception:
        loop_status = None
    loop_line = f"\n  Ветка: {loop_status}" if loop_status else ""
    return (
        f"• {_location_name(location_id)}: опасность {danger}, ур. {_level_text(record)}, "
        f"{_access_label(access)}\n"
        f"  События: {_format_active_events(location_id)}\n"
        f"  Лут: {loot}"
        f"{loop_line}"
    )


def _region_location_ids(region: MapRegion) -> tuple[str, ...]:
    known_ids = {record["id"] for record in get_locations_by_region(region.id)}
    configured = tuple(location_id for location_id in region.location_ids if get_map_location(location_id))
    if configured:
        return configured
    return tuple(sorted(known_ids))


def _region_summary_line(player, region: MapRegion) -> str:
    location_ids = _region_location_ids(region)
    if not location_ids:
        return f"• {region.label}: пока нет точек"

    primary = get_map_location(region.route_target) or get_map_location(location_ids[0])
    access = can_enter_location(player, primary["id"])
    danger = DANGER_LABELS.get(primary.get("danger"), str(primary.get("danger") or "неизвестно"))
    loot = LOOT_PROFILE_LABELS.get(primary.get("loot_profile"), "смешанный лут")
    return (
        f"• {region.label}: опасность {danger}, ур. {_level_text(primary)}, "
        f"{_access_label(access)}. Лут: {loot}"
    )


def get_next_map_step(region_id: str, current_location_id: str) -> tuple[str | None, str]:
    region = MAP_REGIONS.get(region_id)
    if not region:
        return None, "Неизвестный регион."

    target = region.route_target
    location_ids = _region_location_ids(region)
    inner_target = location_ids[1] if len(location_ids) > 1 else None
    current = str(current_location_id or "")

    if region_id == "city":
        if current == "город":
            return None, "Ты в городе. Выбирай городской сервис или иди на КПП для выхода в Зону."
        if current in {"больница", "убежище", "черный рынок"}:
            return "В город", "Следующий шаг: вернуться в город."
        if current == "кпп":
            return "В город", "Следующий шаг: пройти с КПП в город."
        if current in INNER_TO_ROAD_LOCATION:
            return INNER_TO_ROAD_LOCATION[current], "Сначала вернись на предыдущую дорогу, затем на КПП и в город."
        if current in RESEARCH_LOCATIONS:
            return "В КПП", "Сначала вернись на КПП, затем иди в город."
        return "Город", "Следующий шаг: город."

    if inner_target and current == target:
        return LOCATION_COMMAND_LABELS[inner_target], (
            f"Ты у входа в ветку. Можно исследовать дорогу или идти глубже: {LOCATION_COMMAND_LABELS[inner_target]}."
        )
    if inner_target and current == inner_target:
        return None, "Ты во внутренней точке региона. Можно исследовать или вернуться на предыдущую дорогу."
    if current == target:
        return None, "Ты уже у входа в эту ветку. Можно исследовать или вернуться на КПП."
    if current == "кпп":
        return LOCATION_COMMAND_LABELS[target], f"Следующий шаг: {LOCATION_COMMAND_LABELS[target]}."
    if current in INNER_TO_ROAD_LOCATION:
        return INNER_TO_ROAD_LOCATION[current], "Сначала вернись на предыдущую дорогу. Другие ветки открываются через КПП."
    if current in RESEARCH_LOCATIONS:
        return "В КПП", "Сначала вернись на КПП. Другие ветки открываются через КПП."
    if current in CITY_SERVICE_LOCATIONS:
        return "В город", f"Сначала вернись в город, затем иди на КПП -> {region.label}."
    return "КПП", f"Маршрут: {_location_name(current)} -> КПП -> {region.label}. Следующий шаг: КПП."


def format_map_overview(player) -> str:
    current = _current_location_id(player)
    lines = [
        "КАРТА",
        "",
        f"Текущая точка: {_location_name(current)}",
        "",
        "Выбери регион. Карта показывает только ближайшие ветки маршрута, чтобы не превращать экран в список всех мест.",
        "",
    ]
    lines.extend(_region_summary_line(player, MAP_REGIONS[region_id]) for region_id in REGION_ORDER)
    lines.extend(
        [
            "",
            "КПП остается главным узлом выхода в Зону: военный сектор, НИИ и лес открываются через него.",
        ]
    )
    return "\n".join(lines)


def format_region_map(player, region_id: str) -> str:
    region = MAP_REGIONS.get(region_id)
    if not region:
        return format_map_overview(player)

    current = _current_location_id(player)
    next_step, route_text = get_next_map_step(region_id, current)
    lines = [
        f"КАРТА: {region.label.upper()}",
        "",
        region.description,
        "",
        route_text,
        "",
        "Точки региона:",
    ]
    lines.extend(format_location_map_line(player, location_id) for location_id in _region_location_ids(region))
    if next_step:
        lines.extend(["", f"Кнопка маршрута: {next_step}"])
    return "\n".join(lines)


def _parse_region_from_text(text: str) -> str | None:
    normalized = (text or "").strip().lower()
    for prefix in ("карта:", "карта", "map:"):
        if normalized.startswith(prefix):
            normalized = normalized.replace(prefix, "", 1).strip()
            break
    if not normalized:
        return None
    if normalized == "кпп":
        return None
    return REGION_ALIASES.get(normalized)


def is_map_command(text: str) -> bool:
    normalized = (text or "").strip().lower()
    return normalized in {"карта", "карту", "показать карту", "map"} or normalized.startswith("карта:")


def show_map(player, vk, user_id: int, region_id: str | None = None):
    current_ui = get_ui_current_screen(user_id)
    push_current = current_ui.get("name") != "map"
    set_ui_screen(user_id, {"name": "map", "region": region_id or "overview"}, push_current=push_current)

    current_location = _current_location_id(player)
    if region_id and region_id in MAP_REGIONS:
        message = format_region_map(player, region_id)
        keyboard = create_map_region_keyboard(region_id, current_location).get_keyboard()
    else:
        message = format_map_overview(player)
        keyboard = create_map_overview_keyboard(current_location).get_keyboard()

    vk.messages.send(user_id=user_id, message=message, keyboard=keyboard, random_id=0)


def handle_map_command(player, vk, user_id: int, text: str) -> bool:
    if not is_map_command(text):
        return False

    if _current_location_id(player) == "инвентарь":
        vk.messages.send(
            user_id=user_id,
            message="Сначала выйди из инвентаря кнопкой 'Назад'.",
            keyboard=create_inventory_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    show_map(player, vk, user_id, _parse_region_from_text(text))
    return True
