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

from game.constants import RESEARCH_LOCATIONS
from models.npcs import get_npc_by_location, get_npc


# ============================================================
# Helper — стандартный нижний ряд (всегда одинаковый)
# ============================================================

def _add_meta_row(keyboard):
    """Добавить нижний ряд: Персонаж."""
    keyboard.add_button("Персонаж", color=VkKeyboardColor.SECONDARY)


def create_character_keyboard():
    """Экран персонажа: статус, инвентарь, задания."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Статус", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Инвентарь", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Задания", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
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
        keyboard.add_button("КПП", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("Больница", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Убежище", color=VkKeyboardColor.PRIMARY)
        if player_level is not None and player_level >= 25:
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
        keyboard.add_button("Товары", color=VkKeyboardColor.POSITIVE)
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


# ============================================================
# Инвентарь (отдельная клавиатура)
# ============================================================

def create_inventory_keyboard():
    """Клавиатура инвентаря (дублирующая)"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Оружие", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Броня", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Артефакты", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Другое", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Рюкзаки", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Все", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


# ============================================================
# Бой
# ============================================================

def create_combat_keyboard():
    """Клавиатура боя — минимализм в стрессе"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Атаковать", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Навыки", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Инвентарь", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Убежать", color=VkKeyboardColor.NEGATIVE)
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
    _add_meta_row(keyboard)
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
    """Магазин на Чёрном рынке"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Артефакты", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Продать артефакты", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Оружие", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Броня", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Рюкзаки", color=VkKeyboardColor.PRIMARY)
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
    """Главная клавиатура P2P рынка"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("📈 Все лоты", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("🔍 Поиск", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("➕ Выставить лот", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("🧾 Мои лоты", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("🔫 Оружие", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("🛡️ Броня", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("💎 Артефакты", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("💊 Медицина", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("🍖 Еда", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("📒 Мои сделки", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_market_pagination_keyboard(page: int, pages: int, category: str | None = None,
                                       sort: str = "newest", search: str | None = None):
    """Клавиатура с пагинацией и сортировкой для рынка."""
    keyboard = VkKeyboard(one_time=False)

    # Ряд навигации (только назад/вперёд, без номеров страниц).
    # Это гарантирует отсутствие ошибки VK 911 по переполнению строки.
    if page > 1:
        keyboard.add_button("◀️ Назад", color=VkKeyboardColor.SECONDARY)
    if page < pages:
        keyboard.add_button("▶️ Вперёд", color=VkKeyboardColor.SECONDARY)
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
        keyboard.add_button(label, color=color)
        # Держим сортировку в 2 кнопки на ряд, чтобы не ловить лимиты VK.
        if idx % 2 == 0 and idx < len(sort_labels):
            keyboard.add_line()
    keyboard.add_line()

    # Ряд действий
    keyboard.add_button("🔍 Поиск", color=VkKeyboardColor.SECONDARY)
    if category:
        keyboard.add_button("✖️ Сбросить фильтр", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_button("🏠 Главная", color=VkKeyboardColor.NEGATIVE)

    return keyboard


def create_market_listing_keyboard(listing_id: int):
    """Inline-подобная клавиатура для конкретного лота (через текст)."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button(f"🛒 Купить лот {listing_id}", color=VkKeyboardColor.POSITIVE)
    return keyboard


def create_my_listings_keyboard(page: int, pages: int):
    """Клавиатура для управления своими лотами."""
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


def create_market_search_keyboard():
    """Клавиатура для режима поиска."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("✖️ Отмена", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_button("🏠 Главная", color=VkKeyboardColor.SECONDARY)
    return keyboard


def create_purchase_confirm_keyboard():
    """Подтверждение покупки P2P"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("✅ Подтвердить", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("❌ Отмена", color=VkKeyboardColor.NEGATIVE)
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
        "медик": "Медик",
        "дозиметрист": "Дозиметрист",
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

def create_random_event_keyboard(event: dict, stage_index: int = 0):
    """Выбор в случайном событии

    Для мульти-стадийных событий берёт choices из текущей стадии.
    """
    keyboard = VkKeyboard(one_time=False)

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
        keyboard.add_button(choice["label"], color=color)
        keyboard.add_line()
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


def create_emission_impact_keyboard(location: str):
    """Клавиатура во время удара выброса"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("🏃 Бежать в укрытие", color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button("🩺 Лечиться", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("📦 Инвентарь", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Пропустить", color=VkKeyboardColor.SECONDARY)
    return keyboard


def create_emission_risk_confirm_keyboard():
    """Подтверждение выхода из safe во время impact."""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("⚠️ Подтвердить риск", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("Отмена", color=VkKeyboardColor.SECONDARY)
    return keyboard
