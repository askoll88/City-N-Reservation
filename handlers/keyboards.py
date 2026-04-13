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
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

from constants import RESEARCH_LOCATIONS
from npcs import get_npc_by_location, get_npc


# ============================================================
# Helper — стандартный нижний ряд (всегда одинаковый)
# ============================================================

def _add_meta_row(keyboard, show_quests=True):
    """Добавить нижний ряд: Инвентарь | Статус | Задания"""
    keyboard.add_button("Инвентарь", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Статус", color=VkKeyboardColor.SECONDARY)
    if show_quests:
        keyboard.add_line()
        keyboard.add_button("Задания", color=VkKeyboardColor.SECONDARY)


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
    if player_level is not None and player_level >= 25:
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
        keyboard.add_button("Больница", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("КПП", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Убежище", color=VkKeyboardColor.SECONDARY)
        if player_level is not None and player_level >= 25:
            keyboard.add_button("Черный рынок", color=VkKeyboardColor.PRIMARY)
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

    # --- Дороги (исследовательские локации) ---
    elif location_id in RESEARCH_LOCATIONS:
        # Главное действие — исследование
        keyboard.add_button("Исследовать", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        # Возврат
        keyboard.add_button("В КПП", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- Больница ---
    elif location_id == "больница":
        keyboard.add_button("Лечиться", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button("В город", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- Чёрный рынок ---
    elif location_id == "черный рынок":
        keyboard.add_button("Поговорить", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Торговля", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button("Рынок игроков", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Мои лоты", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("В город", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        _add_meta_row(keyboard)

    # --- Убежище ---
    elif location_id == "убежище":
        keyboard.add_button("Поговорить", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Спать", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
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
        keyboard.add_button("Статус", color=VkKeyboardColor.SECONDARY)

    # --- Fallback ---
    else:
        keyboard.add_button("В город", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        _add_meta_row(keyboard)

    return keyboard


# ============================================================
# Инвентарь (отдельная клавиатура)
# ============================================================

def create_inventory_keyboard():
    """Клавиатура инвентаря (дублирующая)"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Все", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Оружие", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Броня", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Рюкзаки", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Артефакты", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Другое", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_button("Статус", color=VkKeyboardColor.SECONDARY)
    return keyboard


# ============================================================
# Бой
# ============================================================

def create_combat_keyboard():
    """Клавиатура боя — минимализм в стрессе"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Атаковать", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Убежать", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("В КПП", color=VkKeyboardColor.PRIMARY)
    return keyboard


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
    """Магазин на Чёрном рынке"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Артефакты", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Продать артефакты", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Оружие", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Броня", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Рюкзаки", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Рынок игроков", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
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

def create_player_market_keyboard():
    """Клавиатура P2P рынка"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Рынок показать", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Мои лоты", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Рынок оружие", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Рынок броня", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Рынок артефакты", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Мои сделки", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_purchase_confirm_keyboard():
    """Подтверждение покупки P2P"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Подтвердить", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Отмена", color=VkKeyboardColor.NEGATIVE)
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
        "местный житель": "Местный житель",
        "наставник": "Наставник",
    }

    for npc in npcs:
        npc_id = npc.id
        button_text = npc_button_map.get(npc_id, npc.name)
        keyboard.add_button(button_text, color=VkKeyboardColor.PRIMARY)

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
    for dialog_id in menu:
        question = npc.get_question_text(dialog_id)
        if question:
            keyboard.add_button(question, color=VkKeyboardColor.SECONDARY)
            keyboard.add_line()

    keyboard.add_button("К выбору NPC", color=VkKeyboardColor.NEGATIVE)
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


# ============================================================
# Случайные события
# ============================================================

def create_random_event_keyboard(event: dict):
    """Выбор в случайном событии"""
    keyboard = VkKeyboard(one_time=False)
    for i, choice in enumerate(event.get("choices", []), 1):
        # Последний вариант обычно «отказ/риск» — красным
        if i == len(event["choices"]) and event.get("type") == "danger":
            color = VkKeyboardColor.NEGATIVE
        else:
            color = VkKeyboardColor.PRIMARY
        keyboard.add_button(choice["label"], color=color)
        keyboard.add_line()
    keyboard.add_button("Пропустить", color=VkKeyboardColor.SECONDARY)
    return keyboard


# ============================================================
# Админка
# ============================================================

def create_admin_keyboard():
    """Админ-панель"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Админ: Пользователи", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Админ: Баны", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("Админ: Маркет ON", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Админ: Маркет OFF", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("Админ: Лоты", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Админ: Помощь", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard
