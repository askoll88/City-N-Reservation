"""
Модуль клавиатур бота
"""
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

from constants import RESEARCH_LOCATIONS
from npcs import get_npc_by_location, get_npc


def create_main_keyboard(player_level: int = None):
    """Главное меню"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Город", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("КПП", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Больница", color=VkKeyboardColor.PRIMARY)
    if player_level is not None and player_level >= 25:
        keyboard.add_button("Черный рынок", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Убежище", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Инвентарь", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Статус", color=VkKeyboardColor.SECONDARY)
    return keyboard


def create_location_keyboard(location_id: str, player_level: int = None):
    """Клавиатура для локации"""
    keyboard = VkKeyboard(one_time=False)

    if location_id == "город":
        keyboard.add_button("Больница", color=VkKeyboardColor.PRIMARY)
        if player_level is not None and player_level >= 25:
            keyboard.add_button("Черный рынок", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("КПП", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Убежище", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Инвентарь", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Статус", color=VkKeyboardColor.SECONDARY)

    elif location_id == "кпп":
        keyboard.add_button("Поговорить", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("В город", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Дорога на военную часть", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Дорога на НИИ", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Дорога на зараженный лес", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Инвентарь", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Статус", color=VkKeyboardColor.SECONDARY)

    elif location_id in RESEARCH_LOCATIONS:
        keyboard.add_button("Исследовать", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button("В КПП", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        keyboard.add_button("Инвентарь", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Статус", color=VkKeyboardColor.SECONDARY)

    elif location_id == "больница":
        keyboard.add_button("Лечиться", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button("В город", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Инвентарь", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Статус", color=VkKeyboardColor.SECONDARY)

    elif location_id == "черный рынок":
        keyboard.add_button("Поговорить", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Торговля", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button("Продать", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Рынок игроков", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("Мои лоты", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("В город", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        keyboard.add_button("Инвентарь", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Статус", color=VkKeyboardColor.SECONDARY)

    elif location_id == "убежище":
        keyboard.add_button("Поговорить", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("В город", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        keyboard.add_button("Инвентарь", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Статус", color=VkKeyboardColor.SECONDARY)

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

    else:
        keyboard.add_button("В город", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Инвентарь", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("Статус", color=VkKeyboardColor.SECONDARY)

    return keyboard


def create_inventory_keyboard():
    """Клавиатура инвентаря"""
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


def create_combat_keyboard():
    """Клавиатура боя"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Атаковать", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Убежать", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("В КПП", color=VkKeyboardColor.PRIMARY)
    return keyboard


def create_shop_keyboard():
    """Клавиатура магазина"""
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
    """Клавиатура магазина у военного на КПП"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Оружие", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Броня", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_scientist_shop_keyboard():
    """Клавиатура магазина у учёного на КПП"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Лекарства", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Энергетики", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_blackmarket_keyboard():
    """Клавиатура магазина на Черном рынке"""
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
    keyboard.add_button("Мои лоты", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_player_market_keyboard():
    """Клавиатура P2P рынка игроков"""
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


def create_admin_keyboard():
    """Клавиатура админки"""
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


def create_artifact_shop_keyboard():
    """Клавиатура магазина артефактов"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Обычные", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Редкие", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Уникальные", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Легендарные", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_npc_select_keyboard(location_id: str):
    """Клавиатура выбора NPC для разговора"""
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
    """Клавиатура диалога с NPC"""
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
