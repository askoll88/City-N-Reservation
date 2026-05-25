"""
Модуль клавиатур бота — User-Friendly интерфейс

ПРИНЦИПЫ ДИЗАЙНА:
1. Навигация сверху — куда можно пойти
2. Действия в середине — что можно сделать
3. Мета-кнопки снизу — инвентарь, статус, задания (всегда доступны)
4. Цветовая логика:
   PRIMARY (синий)   = навигация и основные действия
   POSITIVE (зелёный)= полезные действия (лечение, исследование)
   NEGATIVE (красный)= назад, выход, опасные действия
   SECONDARY (серый) = информация (инвентарь, статус, задания)
5. Максимум 2 кнопки в ряду, максимум 4 ряда
6. Текст кнопок БЕЗ эмодзи — должен совпадать с текстовыми хендлерами
"""
from __future__ import annotations

from vk_api.keyboard import VkKeyboard, VkKeyboardColor

from game.constants import RESEARCH_LOCATIONS
from models.npcs import get_npc_by_location, get_npc

ROAD_TO_INNER_LOCATION = {
    "дорога_военная_часть": ("Военная часть", VkKeyboardColor.PRIMARY),
    "дорога_нии": ("Главный корпус НИИ", VkKeyboardColor.PRIMARY),
    "дорога_зараженный_лес": ("Зараженный лес", VkKeyboardColor.NEGATIVE),
}

INNER_TO_ROAD_LOCATION = {
    "военная_часть": "Дорога на военную часть",
    "склад_17": "Дорога на военную часть",
    "главный_корпус_нии": "Дорога на НИИ",
    "зараженный_лес": "Дорога на зараженный лес",
    "заимка_лесника": "Дорога на зараженный лес",
    "охотничьи_угодья": "Заимка лесника",
    "турбаза_лучик": "Зараженный лес",
    "озеро": "Турбаза Лучик",
}


# ============================================================
# Helper — стандартный нижний ряд (всегда одинаковый)
# ============================================================

def _add_meta_row(keyboard, include_map: bool = False):
    """Добавить нижний ряд мета-навигации."""
    if include_map:
        keyboard.add_button("Карта", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Персонаж", color=VkKeyboardColor.SECONDARY)


def _add_callback_button(keyboard, label: str, *, command: str, color=VkKeyboardColor.SECONDARY, **payload):
    """Добавить callback-кнопку с единым payload."""
    keyboard.add_callback_button(label, color=color, payload={"command": command, **payload})


def create_character_keyboard():
    """Экран персонажа: статус, инвентарь, карта, задания."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Статус", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Инвентарь", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Карта", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Задания", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_status_keyboard(page: int = 0, total_pages: int = 1):
    """Inline-клавиатура вкладок статуса персонажа."""
    total = max(1, int(total_pages or 1))
    current = max(0, min(total - 1, int(page or 0)))
    prev_page = (current - 1) % total
    next_page = (current + 1) % total
    keyboard = VkKeyboard(one_time=False, inline=True)
    _add_callback_button(keyboard, "Пред.", command="status_page", page=prev_page, color=VkKeyboardColor.SECONDARY)
    _add_callback_button(
        keyboard,
        f"{current + 1}/{total}",
        command="status_page",
        page=current,
        color=VkKeyboardColor.PRIMARY,
    )
    _add_callback_button(keyboard, "След.", command="status_page", page=next_page, color=VkKeyboardColor.SECONDARY)
    return keyboard


def create_storage_keyboard(page: int = 0, total_pages: int = 1):
    """Inline-клавиатура страниц шкафа."""
    total = max(1, int(total_pages or 1))
    current = max(0, min(total - 1, int(page or 0)))
    prev_page = (current - 1) % total
    next_page = (current + 1) % total
    keyboard = VkKeyboard(one_time=False, inline=True)
    _add_callback_button(keyboard, "Назад", command="storage_page", page=prev_page, color=VkKeyboardColor.SECONDARY)
    _add_callback_button(
        keyboard,
        f"{current + 1}/{total}",
        command="storage_page",
        page=current,
        color=VkKeyboardColor.PRIMARY,
    )
    _add_callback_button(keyboard, "След.", command="storage_page", page=next_page, color=VkKeyboardColor.SECONDARY)
    return keyboard


def create_shop_hud_keyboard(view: str = "buy", page: int = 0, total_pages: int = 1):
    """Inline-клавиатура страниц витрины/скупки NPC."""
    total = max(1, int(total_pages or 1))
    current = max(0, min(total - 1, int(page or 0)))
    prev_page = (current - 1) % total
    next_page = (current + 1) % total
    safe_view = "sell" if view == "sell" else "buy"
    keyboard = VkKeyboard(one_time=False, inline=True)
    _add_callback_button(
        keyboard,
        "Назад",
        command="shop_page",
        view=safe_view,
        page=prev_page,
        color=VkKeyboardColor.SECONDARY,
    )
    _add_callback_button(
        keyboard,
        f"{current + 1}/{total}",
        command="shop_page",
        view=safe_view,
        page=current,
        color=VkKeyboardColor.PRIMARY,
    )
    _add_callback_button(
        keyboard,
        "След.",
        command="shop_page",
        view=safe_view,
        page=next_page,
        color=VkKeyboardColor.SECONDARY,
    )
    if safe_view == "sell":
        keyboard.add_line()
        _add_callback_button(
            keyboard,
            "Продать весь хлам",
            command="sell_all_trash",
            color=VkKeyboardColor.POSITIVE,
        )
    return keyboard


def create_research_active_keyboard():
    """Минимальная клавиатура на время активного исследования."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Статус исследования", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Отмена", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ============================================================
# Главное меню (/start)
# ============================================================

def create_main_keyboard(player_level: int = None):
    """Главное меню — приветствие"""
    keyboard = VkKeyboard(one_time=False)

    # Навигация
    keyboard.add_button("Город", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("КПП", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Больница", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Черный рынок", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Убежище", color=VkKeyboardColor.SECONDARY)

    # Мета
    keyboard.add_line()
    _add_meta_row(keyboard)

    return keyboard


# ============================================================
# Универсальная клавиатура локации
# ============================================================

def create_location_keyboard(location_id: str, player_level: int = None):
    """Клавиатура для локации — единый паттерн"""

    keyboard = VkKeyboard(one_time=False)

    # --- Город ---
    if location_id == "город":
        keyboard.add_button("КПП", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Больница", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Убежище", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Черный рынок", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- КПП ---
    elif location_id == "кпп":
        # Действия
        keyboard.add_button("Поговорить", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("В город", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        # Дороги (Зона) — сокращённые названия
        keyboard.add_button("Дорога на военную часть", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Дорога на НИИ", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Дорога на зараженный лес", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- Склад 17: домен материалов, без обычного исследования ---
    elif location_id == "склад_17":
        keyboard.add_button("Выбор угрозы", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button("Дорога на военную часть", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- Дороги (исследовательские локации) ---
    elif location_id in RESEARCH_LOCATIONS:
        # Главное действие — исследование
        keyboard.add_button("Исследовать", color=VkKeyboardColor.POSITIVE)
        if location_id == "дорога_военная_часть":
            keyboard.add_button("Склад 17", color=VkKeyboardColor.POSITIVE)
            keyboard.add_line()
            keyboard.add_button("Военная часть", color=VkKeyboardColor.PRIMARY)
        elif location_id == "дорога_зараженный_лес":
            keyboard.add_button("Зараженный лес", color=VkKeyboardColor.NEGATIVE)
            keyboard.add_line()
            keyboard.add_button("Заимка лесника", color=VkKeyboardColor.PRIMARY)
        elif location_id == "зараженный_лес":
            keyboard.add_button("Турбаза Лучик", color=VkKeyboardColor.PRIMARY)
        elif location_id in ROAD_TO_INNER_LOCATION:
            label, color = ROAD_TO_INNER_LOCATION[location_id]
            keyboard.add_button(label, color=color)
        keyboard.add_line()
        # Возврат
        if location_id in INNER_TO_ROAD_LOCATION:
            keyboard.add_button(INNER_TO_ROAD_LOCATION[location_id], color=VkKeyboardColor.NEGATIVE)
        else:
            keyboard.add_button("В КПП", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- Заимка лесника ---
    elif location_id == "заимка_лесника":
        keyboard.add_button("Поговорить", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Отдохнуть", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button("Охотничьи угодья", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button("Дорога на зараженный лес", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- Охотничьи угодья ---
    elif location_id == "охотничьи_угодья":
        keyboard.add_button("Выйти на охоту", color=VkKeyboardColor.POSITIVE)
        keyboard.add_button("Вернуться к меткам", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Заимка лесника", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- Турбаза Лучик ---
    elif location_id == "турбаза_лучик":
        keyboard.add_button("Поговорить", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Отдохнуть", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button("Готовка", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Заказы", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Рыбный шкаф", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Снасти", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Озеро", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button("Зараженный лес", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- Озеро ---
    elif location_id == "озеро":
        keyboard.add_button("Рыбачить", color=VkKeyboardColor.POSITIVE)
        keyboard.add_button("Проверить улов", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Рыбный шкаф", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Турбаза Лучик", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- Больница ---
    elif location_id == "больница":
        keyboard.add_button("Лечиться", color=VkKeyboardColor.POSITIVE)
        keyboard.add_button("Поговорить", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("В город", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- Чёрный рынок ---
    elif location_id == "черный рынок":
        keyboard.add_button("Поговорить", color=VkKeyboardColor.POSITIVE)
        keyboard.add_button("Рынок игроков", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("В город", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- Убежище ---
    elif location_id == "убежище":
        keyboard.add_button("Поговорить", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Спать", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button("Верстак", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Шкаф", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Резонанс Зоны", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("В город", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- Инвентарь ---
    elif location_id == "инвентарь":
        keyboard.add_button("Оружие", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Броня", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Рюкзаки", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Артефакты", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Другое", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)

    # --- Fallback ---
    else:
        keyboard.add_button("В город", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        _add_meta_row(keyboard)

    return keyboard


def create_workbench_keyboard():
    """Верстак убежища: крафт и прокачка оружия."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Крафт", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Улучшение оружия", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Шкаф", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("В город", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    _add_meta_row(keyboard)
    return keyboard


def create_weapon_upgrade_keyboard():
    """Быстрые действия для оружия на верстаке."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Улучшить оружие", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Прорыв оружия", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Крафт", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("В город", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    _add_meta_row(keyboard)
    return keyboard


# ============================================================
# Карта
# ============================================================

def create_map_overview_keyboard(current_location_id: str = None, *, inline: bool = False):
    """Карта: выбор региона без дублирования навигации локаций."""
    keyboard = VkKeyboard(one_time=False, inline=inline)
    _add_callback_button(keyboard, "Город", command="map", region="city", color=VkKeyboardColor.PRIMARY)
    if inline:
        keyboard.add_line()
    _add_callback_button(keyboard, "Военный сектор", command="map", region="military", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "НИИ", command="map", region="science", color=VkKeyboardColor.PRIMARY)
    if inline:
        keyboard.add_line()
    _add_callback_button(keyboard, "Лес", command="map", region="forest", color=VkKeyboardColor.PRIMARY)
    if not inline:
        keyboard.add_line()
        _add_callback_button(keyboard, "Назад", command="back", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_map_region_keyboard(region_id: str, current_location_id: str = None, *, inline: bool = False):
    """Карта выбранного региона: только вкладки карты, без кнопок перемещения."""
    keyboard = VkKeyboard(one_time=False, inline=inline)
    region_tabs = [
        ("Город", "city"),
        ("Военный", "military"),
        ("НИИ", "science"),
        ("Лес", "forest"),
    ]
    for idx, (label, tab_region) in enumerate(region_tabs, 1):
        color = VkKeyboardColor.POSITIVE if tab_region == region_id else VkKeyboardColor.SECONDARY
        _add_callback_button(keyboard, label, command="map", region=tab_region, color=color)
        if inline and idx < len(region_tabs):
            keyboard.add_line()
        elif not inline and idx == 2:
            keyboard.add_line()
    keyboard.add_line()
    _add_callback_button(keyboard, "Обзор", command="map", region="overview", color=VkKeyboardColor.PRIMARY)
    if not inline:
        _add_callback_button(keyboard, "Назад", command="back", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ============================================================
# Инвентарь (отдельная клавиатура)
# ============================================================

def create_inventory_keyboard(*, inline: bool = False):
    """Клавиатура инвентаря. Всегда нижняя, не inline."""
    keyboard = VkKeyboard(one_time=False)
    _add_callback_button(keyboard, "Оружие", command="inventory_section", section="weapons", color=VkKeyboardColor.PRIMARY)
    _add_callback_button(keyboard, "Броня", command="inventory_section", section="armor", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "Артефакты", command="inventory_section", section="artifacts", color=VkKeyboardColor.PRIMARY)
    _add_callback_button(keyboard, "Рюкзаки", command="inventory_section", section="backpacks", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "Хлам", command="inventory_section", section="trash", color=VkKeyboardColor.SECONDARY)
    _add_callback_button(keyboard, "Другое", command="inventory_section", section="other", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "Все", command="inventory_section", section="all", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "Назад", command="inventory_back", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_inventory_hud_keyboard(section: str = "all", page: int = 0, total_pages: int = 1):
    """Inline-клавиатура HUD инвентаря: страницы текущего раздела."""
    total = max(1, int(total_pages or 1))
    current = max(0, min(total - 1, int(page or 0)))
    prev_page = (current - 1) % total
    next_page = (current + 1) % total
    keyboard = VkKeyboard(one_time=False, inline=True)
    _add_callback_button(keyboard, "Назад", command="inventory_page", section=section, page=prev_page, color=VkKeyboardColor.SECONDARY)
    _add_callback_button(
        keyboard,
        f"{current + 1}/{total}",
        command="inventory_page",
        section=section,
        page=current,
        color=VkKeyboardColor.PRIMARY,
    )
    _add_callback_button(keyboard, "След.", command="inventory_page", section=section, page=next_page, color=VkKeyboardColor.SECONDARY)
    return keyboard


# ============================================================
# Бой
# ============================================================

def create_combat_keyboard():
    """Клавиатура боя — минимализм в стрессе"""
    keyboard = VkKeyboard(one_time=False)
    _add_callback_button(keyboard, "Атаковать", command="combat_action", action="attack", color=VkKeyboardColor.POSITIVE)
    _add_callback_button(keyboard, "Навыки", command="combat_action", action="skills", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "Инвентарь", command="combat_action", action="inventory", color=VkKeyboardColor.PRIMARY)
    _add_callback_button(keyboard, "Убежать", command="combat_action", action="flee", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ============================================================
# Переход (Travel Corridor)
# ============================================================

def create_travel_keyboard():
    """Клавиатура коридора перехода между локациями."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Идти", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Осмотреться", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Ускориться", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Отмена пути", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    _add_meta_row(keyboard, include_map=False)
    return keyboard


def create_hunting_grounds_keyboard(active: bool = False):
    """Клавиатура охотничьих угодий."""
    keyboard = VkKeyboard(one_time=False)
    if active:
        keyboard.add_button("Вернуться к меткам", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Снять метки", color=VkKeyboardColor.NEGATIVE)
    else:
        keyboard.add_button("Тихая тропа", color=VkKeyboardColor.POSITIVE)
        keyboard.add_button("Засада у солонца", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Глубокий след", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_button("Заимка лесника", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    _add_meta_row(keyboard)
    return keyboard


def create_pale_watcher_scene_keyboard(label: str = "Дальше"):
    """Inline-кнопка для пошаговой сцены лесной легенды."""
    keyboard = VkKeyboard(one_time=False, inline=True)
    _add_callback_button(
        keyboard,
        label,
        command="pale_watcher_scene",
        action="next",
        color=VkKeyboardColor.PRIMARY,
    )
    return keyboard


def create_fishing_keyboard(active: bool = False):
    """Клавиатура рыбалки у озера."""
    keyboard = VkKeyboard(one_time=False)
    if active:
        keyboard.add_button("Проверить улов", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Отменить рыбалку", color=VkKeyboardColor.NEGATIVE)
    else:
        keyboard.add_button("Береговая снасть", color=VkKeyboardColor.POSITIVE)
        keyboard.add_button("Глубокий заброс", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Аномальная заводь", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_button("Турбаза Лучик", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    _add_meta_row(keyboard)
    return keyboard


def create_fishing_fight_keyboard():
    """Клавиатура короткого вываживания рыбы."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Вываживать", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Удерживать", color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button("Стравить леску", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Рывок", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    _add_meta_row(keyboard)
    return keyboard


def create_forester_trial_keyboard(stage: str):
    """Клавиатура испытания Лесника."""
    keyboard = VkKeyboard(one_time=False)
    if stage == "tracks":
        keyboard.add_button("Снять слепок следа", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Проверить кровь", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Замереть на шум", color=VkKeyboardColor.SECONDARY)
    elif stage == "wind":
        keyboard.add_button("Проверить ветер", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Срезать просеку", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Обойти валежник", color=VkKeyboardColor.SECONDARY)
    elif stage == "bait":
        keyboard.add_button("Осмотреть периметр", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Снять трофей", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Выждать дистанцию", color=VkKeyboardColor.SECONDARY)
    elif stage == "shot":
        keyboard.add_button("Ждать разворот", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Бить по силуэту", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Сместиться ниже", color=VkKeyboardColor.SECONDARY)
    else:
        keyboard.add_button("Пометить тропу", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Добрать сразу", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Слушать стаю", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("К выбору NPC", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_resume_keyboard(location_id: str, player_level: int = None, user_id: int = None):
    """
    Вернуть клавиатуру текущего контекста.
    Если игрок всё ещё в коридоре перехода, нужно продолжать показывать travel UI.
    """
    if user_id is not None:
        try:
            from infra.state_manager import has_travel_state
            if has_travel_state(user_id):
                return create_travel_keyboard()
        except Exception:
            pass
    return create_location_keyboard(location_id, player_level)


# ============================================================
# Магазины
# ============================================================

def create_shop_keyboard():
    """Общая клавиатура магазина"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Оружие", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Броня", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Рюкзаки", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Артефакты", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Медицина", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Ресурсы", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_kpp_shop_keyboard():
    """Магазин военного на КПП"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Оружие", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Броня", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Продать", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_scientist_shop_keyboard():
    """Магазин учёного на КПП"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Лекарства", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Энергетики", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_blackmarket_keyboard():
    """Интерфейс Черного рынка (торговля + P2P)."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Поговорить", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Рынок игроков", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Купить", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Продать", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_heal_confirm_keyboard(*, inline: bool = False):
    """Клавиатура подтверждения лечения (показывается только после расчета цены)."""
    keyboard = VkKeyboard(one_time=False, inline=inline)
    _add_callback_button(keyboard, "Подтвердить лечение", command="heal_confirm", action="confirm", color=VkKeyboardColor.POSITIVE)
    _add_callback_button(keyboard, "Отмена лечения", command="heal_confirm", action="cancel", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_artifact_shop_keyboard():
    """Магазин артефактов по редкости"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Обычные", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Редкие", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Уникальные", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Легендарные", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ============================================================
# P2P Рынок игроков
# ============================================================

def create_player_market_keyboard(*, inline: bool = False):
    """Главная клавиатура P2P рынка. Всегда нижняя, не inline."""
    keyboard = VkKeyboard(one_time=False)
    _add_callback_button(keyboard, "📈 Все лоты", command="market_open", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("🔍 Поиск", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("➕ Выставить лот", color=VkKeyboardColor.POSITIVE)
    _add_callback_button(keyboard, "🧾 Мои лоты", command="market_my_listings", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "🔫 Оружие", command="market_category", category="weapons", color=VkKeyboardColor.PRIMARY)
    _add_callback_button(keyboard, "🛡️ Броня", command="market_category", category="armor", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "💎 Артефакты", command="market_category", category="artifacts", color=VkKeyboardColor.PRIMARY)
    _add_callback_button(keyboard, "💊 Медицина", command="market_category", category="meds", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "🍖 Еда", command="market_category", category="food", color=VkKeyboardColor.SECONDARY)
    _add_callback_button(keyboard, "📒 Мои сделки", command="market_transactions", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_market_pagination_keyboard(page: int, pages: int, category: str | None = None,
                                       sort: str = "newest", search: str | None = None,
                                       *, inline: bool = False):
    """Клавиатура с пагинацией и сортировкой для рынка."""
    keyboard = VkKeyboard(one_time=False, inline=inline)

    if inline:
        if page > 1:
            _add_callback_button(keyboard, "◀️ Пред.", command="market_page", page=page - 1, color=VkKeyboardColor.SECONDARY)
        if page < pages:
            _add_callback_button(keyboard, "▶️ Вперёд", command="market_page", page=page + 1, color=VkKeyboardColor.SECONDARY)
        return keyboard

    # Ряд навигации (только назад/вперёд, без номеров страниц).
    # Это гарантирует отсутствие ошибки VK 911 по переполнению строки.
    if page > 1:
        _add_callback_button(keyboard, "◀️ Назад", command="market_page", page=page - 1, color=VkKeyboardColor.SECONDARY)
    if page < pages:
        _add_callback_button(keyboard, "▶️ Вперёд", command="market_page", page=page + 1, color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()

    # Ряд сортировки
    sort_labels = [
        ("🆕 Новые", "newest"),
        ("📅 Старые", "oldest"),
        ("💰 Дешевле", "cheap"),
        ("💎 Дороже", "expensive"),
    ]
    for idx, (label, sort_key) in enumerate(sort_labels, 1):
        color = VkKeyboardColor.POSITIVE if sort == sort_key else VkKeyboardColor.SECONDARY
        _add_callback_button(keyboard, label, command="market_sort", sort=sort_key, color=color)
        # Держим сортировку в 2 кнопки на ряд, чтобы не ловить лимиты VK.
        if idx % 2 == 0 and idx < len(sort_labels):
            keyboard.add_line()
    keyboard.add_line()

    # Ряд действий
    keyboard.add_button("🔍 Поиск", color=VkKeyboardColor.SECONDARY)
    if category:
        _add_callback_button(keyboard, "✖️ Сбросить фильтр", command="market_clear_filter", color=VkKeyboardColor.NEGATIVE)
    _add_callback_button(keyboard, "🏠 Главная", command="market_home", color=VkKeyboardColor.NEGATIVE)

    return keyboard


def create_market_listing_keyboard(listing_id: int):
    """Inline-подобная клавиатура для конкретного лота (через текст)."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button(f"🛒 Купить лот {listing_id}", color=VkKeyboardColor.POSITIVE)
    return keyboard


def create_my_listings_keyboard(page: int, pages: int, *, inline: bool = False):
    """Клавиатура для управления своими лотами. Всегда нижняя, не inline."""
    keyboard = VkKeyboard(one_time=False)

    if pages > 1:
        if page > 1:
            keyboard.add_button("◀️ Назад", color=VkKeyboardColor.SECONDARY)
        if page < pages:
            keyboard.add_button("▶️ Вперёд", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()

    keyboard.add_button("📋 Активные", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("✅ Проданные", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("📊 Все", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("📈 Все лоты", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("🏠 Главная", color=VkKeyboardColor.NEGATIVE)

    return keyboard


def create_market_search_keyboard(*, inline: bool = False):
    """Клавиатура для режима поиска. Всегда нижняя, не inline."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("✖️ Отмена", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_button("🏠 Главная", color=VkKeyboardColor.SECONDARY)
    return keyboard


def create_purchase_confirm_keyboard(*, inline: bool = False):
    """Подтверждение покупки P2P"""
    keyboard = VkKeyboard(one_time=False, inline=inline)
    _add_callback_button(keyboard, "✅ Подтвердить", command="market_purchase", action="confirm", color=VkKeyboardColor.POSITIVE)
    _add_callback_button(keyboard, "❌ Отмена", command="market_purchase", action="cancel", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ============================================================
# NPC и диалоги
# ============================================================

def create_npc_select_keyboard(location_id: str):
    """Выбор NPC для разговора"""
    keyboard = VkKeyboard(one_time=False)
    npcs = get_npc_by_location(location_id)

    npc_button_map = {
        "военный": "Военный",
        "ученый": "Учёный",
        "барыга": "Барыга",
        "местный житель": "Проводник",
        "наставник": "Инструктор классов",
        "ранговик": "Куратор рангов",
        "медик": "Медик",
        "дозиметрист": "Дозиметрист",
    }

    split_index = None
    if location_id == "убежище" and len(npcs) > 1:
        # В убежище раскладываем NPC на два ряда, чтобы интерфейс был чище.
        split_index = (len(npcs) + 1) // 2

    for idx, npc in enumerate(npcs, start=1):
        npc_id = npc.id
        button_text = npc_button_map.get(npc_id, npc.name)
        keyboard.add_button(button_text, color=VkKeyboardColor.PRIMARY)
        if split_index and idx == split_index and idx < len(npcs):
            keyboard.add_line()

    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_npc_dialog_keyboard(npc_id: str):
    """Диалог с NPC"""
    keyboard = VkKeyboard(one_time=False)
    npc = get_npc(npc_id)
    if not npc:
        return create_location_keyboard("кпп")

    menu = npc.get_menu()
    row_buttons = 0
    for dialog_id in menu:
        question = npc.get_question_text(dialog_id)
        if question:
            keyboard.add_button(question, color=VkKeyboardColor.SECONDARY)
            row_buttons += 1
            if row_buttons >= 2:
                keyboard.add_line()
                row_buttons = 0
    if row_buttons:
        keyboard.add_line()
    keyboard.add_button("К выбору NPC", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_warehouse17_threat_keyboard(player):
    """Выбор уровня угрозы оружейного данжа."""
    from game.weapon_dungeons import get_available_warehouse17_threats

    rank_tier = player._get_rank_tier() if hasattr(player, "_get_rank_tier") else getattr(player, "rank_tier", 1)
    threats = get_available_warehouse17_threats(rank_tier)
    keyboard = VkKeyboard(one_time=False)
    row_count = 0
    for threat in threats:
        keyboard.add_button(threat.label, color=VkKeyboardColor.PRIMARY)
        row_count += 1
        if row_count >= 2:
            keyboard.add_line()
            row_count = 0
    if row_count:
        keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_class_selection_keyboard():
    """Отдельная клавиатура выбора класса у инструктора."""
    keyboard = VkKeyboard(one_time=False)
    from models.classes import get_all_classes

    mentor = get_npc("наставник")
    row_buttons = 0
    for class_id in get_all_classes().keys():
        label = mentor.get_question_text(class_id) if mentor else None
        if not label:
            label = class_id
        keyboard.add_button(label, color=VkKeyboardColor.PRIMARY)
        row_buttons += 1
        if row_buttons >= 2:
            keyboard.add_line()
            row_buttons = 0

    if row_buttons:
        keyboard.add_line()
    keyboard.add_button("Назад к инструктору", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_class_confirm_keyboard():
    """Клавиатура подтверждения выбранного класса."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Подтвердить выбор", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Отмена", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ============================================================
# Ежедневные задания
# ============================================================

def create_daily_quests_keyboard():
    """Ежедневные задания"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Мои задания", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Забрать награду", color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_quests_keyboard(page: int = 0, total_pages: int = 3):
    """Постраничная клавиатура общей вкладки заданий."""
    total = max(1, int(total_pages or 1))
    current = max(0, min(total - 1, int(page or 0)))
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Задания назад", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button(f"{current + 1}/{total}", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Задания далее", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Активные задания", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Дейлики", color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button("Забрать награду", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ============================================================
# Случайные события
# ============================================================

def create_random_event_keyboard(event: dict, stage_index: int = 0, *, inline: bool = False):
    """Выбор в случайном событии

    Для мульти-стадийных событий берёт choices из текущей стадии.
    """
    keyboard = VkKeyboard(one_time=False, inline=inline)

    # Мульти-стадийные события: choices внутри каждой стадии
    if event.get("type") == "multi_stage":
        stages = event.get("stages", [])
        if stage_index >= len(stages):
            stage_index = len(stages) - 1
        if stage_index < 0:
            stage_index = 0
        choices = stages[stage_index].get("choices", [])
    else:
        choices = event.get("choices", [])

    for i, choice in enumerate(choices, 1):
        # Последний вариант обычно «отказ/риск» — красным
        if i == len(choices) and event.get("type") == "danger":
            color = VkKeyboardColor.NEGATIVE
        else:
            color = VkKeyboardColor.PRIMARY
        if inline:
            _add_callback_button(keyboard, choice["label"], command="random_event", action="choice", choice=i - 1, color=color)
        else:
            keyboard.add_button(choice["label"], color=color)
        keyboard.add_line()
    if inline:
        _add_callback_button(keyboard, "Пропустить", command="random_event", action="skip", color=VkKeyboardColor.SECONDARY)
    else:
        keyboard.add_button("Пропустить", color=VkKeyboardColor.SECONDARY)
    return keyboard


# ============================================================
# Админка — категории и подменю
# ============================================================

def create_admin_keyboard():
    """Главная админ-панель — категории"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("👥 Пользователи", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("☢️ Выброс", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("📦 Выдача", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("🎲 Ивенты", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("🏪 Маркет", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("❓ Помощь", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("🌀 Резонанс", color=VkKeyboardColor.POSITIVE)
    return keyboard


# ---------- Пользователи ----------

def create_admin_users_keyboard():
    """Подменю: Пользователи"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Последние пользователи", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Забаненные", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("Профиль (по vk_id)", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Инвентарь (по vk_id)", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Права on/off", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Локация (телепорт)", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("⬅️ Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_admin_users_list_keyboard(page: int = 1, pages: int = 1):
    """Пагинация списка пользователей в админке."""
    keyboard = VkKeyboard(one_time=False)
    page = max(1, int(page or 1))
    pages = max(1, int(pages or 1))
    has_nav = False

    if page > 1:
        keyboard.add_button("◀️ Игроки", color=VkKeyboardColor.SECONDARY)
        has_nav = True
    if page < pages:
        if page > 1:
            keyboard.add_line()
        keyboard.add_button("Игроки ▶️", color=VkKeyboardColor.PRIMARY)
        has_nav = True
    if has_nav:
        keyboard.add_line()
    keyboard.add_button("👥 Пользователи", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("⬅️ Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ---------- Выброс ----------

def create_admin_emission_keyboard():
    """Подменю: Выброс"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("☢️ Запустить выброс", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_button("⛔ Отменить выброс", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("📊 Статус выброса", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("⬅️ Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ---------- Выдача ----------

def create_admin_give_keyboard():
    """Подменю: Выдача"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("🎁 Выдать предмет", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("🗑️ Удалить предмет", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("📝 Set поле (статы)", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("⬅️ Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ---------- Ивенты ----------

def create_admin_events_keyboard():
    """Подменю: Ивенты"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("🎲 Рандом ивент игроку", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("📋 Квесты игрока", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("🌐 Ивент статус", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("🚀 Старт ивента", color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button("⚡ Резонанс", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("☠️ Хищники", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("🎒 Мародёры", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("🛑 Стоп ивента", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("⏰ Кулдаун инфо", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("⏰ Кулдаун снять", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("👥 Онлайн", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("⬅️ Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ---------- Маркет ----------

def create_admin_market_keyboard():
    """Подменю: Маркет"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("📋 Активные лоты", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("🗂️ Все лоты", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("✅ Маркет ON", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("⛔ Маркет OFF", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("✖️ Снять лот", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("⬅️ Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ---------- Резонанс Зоны ----------

def create_admin_gacha_keyboard():
    """Подменю: Резонанс Зоны"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("🟢 Гача ON", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("🔴 Гача OFF", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("📊 Гача статус", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("💠 Выдать осколки", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("📈 Гача статистика", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("🗓️ Баннеры", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("⬅️ Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ---------- Помощь ----------

def create_admin_help_keyboard():
    """Подменю: Помощь"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("❓ Справка", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("⬅️ Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ============================================================
# Выброс (Emission)
# ============================================================

def create_emission_warning_keyboard():
    """Клавиатура для предупреждения о выбросе"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("🏃 Бежать в укрытие", color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button("😰 Остаться и рискнуть", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("Пропустить", color=VkKeyboardColor.SECONDARY)
    return keyboard


def create_emission_impact_keyboard(location: str, can_flee: bool = True):
    """Клавиатура во время удара выброса"""
    keyboard = VkKeyboard(one_time=False)
    if can_flee:
        keyboard.add_button("🏃 Бежать в укрытие", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
    keyboard.add_button("🩺 Лечиться", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("📦 Инвентарь", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Пропустить", color=VkKeyboardColor.SECONDARY)
    return keyboard


def create_emission_risk_confirm_keyboard(*, inline: bool = False):
    """Подтверждение выхода из safe во время impact."""
    keyboard = VkKeyboard(one_time=False, inline=inline)
    _add_callback_button(keyboard, "⚠️ Подтвердить риск", command="emission_risk", action="confirm", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    _add_callback_button(keyboard, "Отмена", command="emission_risk", action="cancel", color=VkKeyboardColor.SECONDARY)
    return keyboard
