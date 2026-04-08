"""
VK S.T.A.L.K.E.R. Бот - Главный файл
"""
import logging
import os
import sys
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("Loading main.py...")

load_dotenv()

# Отладка - проверяем загрузку переменных
DEBUG_TOKEN = os.getenv('VK_TOKEN')
DEBUG_GROUP = os.getenv('GROUP_ID')
token_preview = (DEBUG_TOKEN[:20] + '...') if DEBUG_TOKEN and len(DEBUG_TOKEN) > 20 else (DEBUG_TOKEN if DEBUG_TOKEN else 'NOT_FOUND')
logger.debug(f"After load_dotenv: TOKEN={token_preview}, GROUP={DEBUG_GROUP}")

import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

import database
import player as player_module
from locations import get_location
from constants import RESEARCH_LOCATIONS
from handlers.location import (
    go_to_location, go_to_inventory, go_back, 
    handle_sleep, handle_heal, get_status, show_welcome
)
from handlers.inventory import (
    handle_inventory_digit, show_weapons, show_armor, 
    show_backpacks, show_artifacts, show_other,
    show_equipped_artifacts, show_artifact_slots, show_artifact_help,
    handle_use_item, handle_buy_item, handle_sell_item, 
    handle_buy_artifact_slot, handle_equip_backpack, handle_unequip_backpack
)
from handlers.combat import handle_explore, handle_combat_attack, handle_combat_flee, _combat_state as combat_state_module, _anomaly_state, handle_anomaly_action
from npcs import get_npc_by_location, get_npc


# === Глобальное состояние ===
# Важно: используем _combat_state из handlers.combat для синхронизации с потоками
_combat_state = combat_state_module  # Ссылка на общее состояние боя
_players_cache = {}  # Кэш игроков
_dialog_state = {}  # Хранит состояние диалога с NPC: {user_id: {"npc": "военный", "stage": "greeting|menu"}}
_menu_state = {}  # Хранит состояние меню: {user_id: {"state": "status", "previous_location": "город"}}


# === Настройки VK ===
TOKEN = os.getenv('VK_TOKEN', '')
GROUP_ID = os.getenv('GROUP_ID', '')


# === Работа с игроками ===
def get_player(user_id: int):
    """Получить или создать игрока"""
    if user_id not in _players_cache:
        _players_cache[user_id] = player_module.Player(user_id)
    return _players_cache[user_id]


# === Клавиатуры ===
def create_main_keyboard():
    """Главное меню"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Город", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("КПП", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Больница", color=VkKeyboardColor.PRIMARY)
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
        # Черный рынок только для 25+ уровня (если уровень передан)
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
    keyboard.add_button("В город", color=VkKeyboardColor.NEGATIVE)
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


def create_npc_select_keyboard(location_id: str):
    """Клавиатура выбора NPC для разговора"""
    keyboard = VkKeyboard(one_time=False)
    npcs = get_npc_by_location(location_id)

    for npc in npcs:
        npc_id = npc.id
        if npc_id == "военный":
            keyboard.add_button("Военный", color=VkKeyboardColor.PRIMARY)
        elif npc_id == "ученый":
            keyboard.add_button("Учёный", color=VkKeyboardColor.PRIMARY)
        elif npc_id == "барыга":
            keyboard.add_button("Барыга", color=VkKeyboardColor.PRIMARY)
        elif npc_id == "местный житель":
            keyboard.add_button("Местный житель", color=VkKeyboardColor.PRIMARY)
        elif npc_id == "наставник":
            keyboard.add_button("Наставник", color=VkKeyboardColor.PRIMARY)

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


def show_npc_dialog(player, vk, user_id: int, npc_id: str, dialog_id: str = None):
    """Показать диалог с NPC"""
    import sys
    print(f"[DEBUG] show_npc_dialog: user={user_id}, npc={npc_id}, dialog_id={dialog_id}", file=sys.stderr)

    npc = get_npc(npc_id)
    if not npc:
        vk.messages.send(
            user_id=user_id,
            message="😶 NPC не найден.",
            random_id=0
        )
        return

    # Если это начало диалога - показываем приветствие
    if dialog_id is None:
        _dialog_state[user_id] = {"npc": npc_id, "stage": "menu"}
        vk.messages.send(
            user_id=user_id,
            message=npc.greeting,
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return

    # Получаем ответ на конкретный вопрос
    dialog = npc.get_dialog(dialog_id)
    if not dialog:
        vk.messages.send(
            user_id=user_id,
            message="NPC не понимает тебя.",
            random_id=0
        )
        return

    answer = dialog.get("answer", "NPC молчит.")
    next_stage = dialog.get("next")

    # Обработка набора новичка
    if dialog_id == "набор":
        import database
        result = database.give_newbie_kit(user_id)
        # Очищаем состояние диалога
        if user_id in _dialog_state:
            del _dialog_state[user_id]

        if result is None:
            # Игрок уже получал набор
            vk.messages.send(
                user_id=user_id,
                message="👴 Местный житель:\n\n«Эй, я уже давал тебе набор! Не жадничай, сталкер. Иди в Зону — там добудешь всё сам.»",
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
        else:
            # Инвалидируем кэш игрока и обновляем инвентарь
            from player import invalidate_player_cache
            invalidate_player_cache(user_id)
            player = get_player(user_id)
            player.inventory.reload()
            # Формируем список выданных предметов
            items_list = "\n".join([f"• {name} x{qty}" for name, qty in result["items"]])
            vk.messages.send(
                user_id=user_id,
                message=f"{answer}\n\n📦 <b>Получено:</b>\n{items_list}\n\n💰 Деньги: 10000 руб.",
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
        return

    # Обработка получения класса персонажа
    CLASS_CHANGE_COST = 500000  # Цена смены класса

    if dialog_id == "get_class":
        # Проверяем уровень
        if player.level < 10:
            vk.messages.send(
                user_id=user_id,
                message="🎓 <b>Наставник:</b>\n\n«Ты ещё слишком слаб, сталкер. Приходи, когда достигнешь 10 уровня. К тому времени я посмотрю, на что ты способен.»",
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0
            )
            return

        # Проверяем оружие
        if not player.equipped_weapon:
            vk.messages.send(
                user_id=user_id,
                message="🎓 <b>Наставник:</b>\n\n«У тебя нет оружия! Как ты собираешься выживать в Зоне? Экипируй оружие и приходи снова.»",
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0
            )
            return

        # Определяем класс по оружию
        from classes import get_class_by_weapon, format_class_info
        class_id = get_class_by_weapon(player.equipped_weapon)

        if not class_id:
            vk.messages.send(
                user_id=user_id,
                message="🎓 <b>Наставник:</b>\n\n«Хм, это оружие мне не знакомо. Приходи с другим — я посмотрю, какой стиль боя тебе подходит.»",
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0
            )
            return

        # Если класс уже есть - проверяем деньги на смену
        if player.player_class and player.player_class != class_id:
            if player.money < CLASS_CHANGE_COST:
                vk.messages.send(
                    user_id=user_id,
                    message=f"🎓 <b>Наставник:</b>\n\n«Ты уже имеешь класс, но хочешь сменить на {class_id.upper()}. Это стоит {CLASS_CHANGE_COST:,} руб.\n\nУ тебя недостаточно денег — нужно ещё {CLASS_CHANGE_COST - player.money:,} руб.»",
                    keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                    random_id=0
                )
                return

            # Списываем деньги и меняем класс
            from player import invalidate_player_cache
            new_money = player.money - CLASS_CHANGE_COST
            database.update_user_stats(user_id, money=new_money, player_class=class_id)
            invalidate_player_cache(user_id)
            player = get_player(user_id)

            class_info = format_class_info(class_id)
            vk.messages.send(
                user_id=user_id,
                message=f"💰 <b>Наставник:</b>\n\n«Переобучение прошло успешно! Списано {CLASS_CHANGE_COST:,} руб.\n\nТеперь ты — {class_id.split()[0]} {class_id.upper()}.\n\n{class_info}\n\n'Запомни: сила класса — в оружии. Меняй оружие — меняется и класс!'»",
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0
            )
            return

        # Если класса ещё нет - просто выдаём
        from player import invalidate_player_cache
        database.update_user_stats(user_id, player_class=class_id)
        invalidate_player_cache(user_id)
        player = get_player(user_id)

        class_info = format_class_info(class_id)
        vk.messages.send(
            user_id=user_id,
            message=f"🎓 <b>Наставник:</b>\n\n«Отлично! Теперь ты — {class_id.split()[0]} {class_id.upper()}. Вот твои навыки:\n\n{class_info}\n\n'Запомни: сила класса — в оружии. Меняй оружие — меняется и класс!'»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return

    # Обработка смены класса (явная команда)
    if dialog_id == "change_class":
        if player.level < 10:
            vk.messages.send(
                user_id=user_id,
                message="🎓 <b>Наставник:</b>\n\n«Ты ещё слишком слаб для смены класса. Приходи на 10 уровне.»",
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0
            )
            return

        if not player.equipped_weapon:
            vk.messages.send(
                user_id=user_id,
                message="🎓 <b>Наставник:</b>\n\n«Экипируй оружие, на которое хочешь перейти, и приходи снова.»",
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0
            )
            return

        from classes import get_class_by_weapon, format_class_info
        new_class_id = get_class_by_weapon(player.equipped_weapon)

        if not new_class_id:
            vk.messages.send(
                user_id=user_id,
                message="🎓 <b>Наставник:</b>\n\n«Это оружие мне не знакомо. Приходи с другим.»",
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0
            )
            return

        if new_class_id == player.player_class:
            vk.messages.send(
                user_id=user_id,
                message=f"🎓 <b>Наставник:</b>\n\n«У тебя уже есть класс {player.player_class.upper()}. Экипируй другое оружие для смены.»",
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0
            )
            return

        # Проверяем деньги
        if player.money < CLASS_CHANGE_COST:
            vk.messages.send(
                user_id=user_id,
                message=f"🎓 <b>Наставник:</b>\n\n«Смена класса на {new_class_id.upper()} стоит {CLASS_CHANGE_COST:,} руб.\n\nУ тебя есть {player.money:,} руб. Не хватает {CLASS_CHANGE_COST - player.money:,} руб.»",
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0
            )
            return

        # Списываем деньги и меняем класс
        from player import invalidate_player_cache
        new_money = player.money - CLASS_CHANGE_COST
        database.update_user_stats(user_id, money=new_money, player_class=new_class_id)
        invalidate_player_cache(user_id)
        player = get_player(user_id)

        class_info = format_class_info(new_class_id)
        vk.messages.send(
            user_id=user_id,
            message=f"💰 <b>Наставник:</b>\n\n«Класс успешно сменён! Списано {CLASS_CHANGE_COST:,} руб.\n\nТеперь ты — {new_class_id.split()[0]} {new_class_id.upper()}.\n\n{class_info}\n\n'Запомни: сила класса — в оружии!'»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return

    # Обработка просмотра своего класса
    if dialog_id == "my_class":
        if not player.player_class:
            vk.messages.send(
                user_id=user_id,
                message="🎓 <b>Наставник:</b>\n\n«У тебя ещё нет класса! Приходи, когда достигнешь 10 уровня и экипируй оружие. Я обучу тебя боевому стилю.»",
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0
            )
            return

        # Показываем текущий класс с учётом уровня игрока
        class_info = format_class_info(player.player_class, player.level)

        # Также показываем текущий класс, основанный на оружии
        current_weapon = player.equipped_weapon or "нет"
        from classes import get_class_by_weapon, format_passive_status
        current_class = get_class_by_weapon(current_weapon) if current_weapon != "нет" else None

        msg = f"🎓 <b>Наставник:</b>\n\n"
        msg += f"📌 <b>Твой текущий класс:</b> {player.player_class.upper()}\n"
        msg += f"🔫 <b>Экипированное оружие:</b> {current_weapon}\n"
        msg += f"⭐ <b>Твой уровень:</b> {player.level}\n\n"

        if current_class and current_class != player.player_class:
            msg += f"⚠️ <b>Внимание!</b> Твой экипированный класс: {current_class.upper()}\n"
            msg += "Класс меняется в зависимости от оружия!\n\n"

        # Показываем статус пассивных навыков
        passive_status = format_passive_status(player.player_class, player.level)
        msg += f"{passive_status}\n"

        # Показываем активные навыки
        msg += f"<b>Информация о классе:</b>\n{class_info}"

        vk.messages.send(
            user_id=user_id,
            message=msg,
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return

    # Проверяем, не является ли ответ специальной командой (магазин/продажа)
    if next_stage in ["shop_menu", "shop_weapons", "shop_armor", "shop_meds", "shop_artifacts", "sell_items", "sell_gear"]:
        _dialog_state[user_id] = {"npc": npc_id, "stage": next_stage}
        # Перенаправляем в магазин
        if next_stage == "shop_menu":
            # Меню выбора категорий у военного
            vk.messages.send(
                user_id=user_id,
                message="🎖️ <b>Военный:</b>\n\n«Выбирай, сталкер:\n\n🔫 Оружие — от пистолетов до автоматов\n🛡️ Броня — жилеты и шлемы\n\nЦены — как есть, торга не будет.»",
                keyboard=create_kpp_shop_keyboard().get_keyboard(),
                random_id=0
            )
        elif next_stage == "shop_weapons":
            from handlers.inventory import show_soldier_weapons
            show_soldier_weapons(player, vk, user_id)
        elif next_stage == "shop_armor":
            from handlers.inventory import show_soldier_armor
            show_soldier_armor(player, vk, user_id)
        elif next_stage == "shop_meds":
            from handlers.inventory import show_scientist_shop
            show_scientist_shop(player, vk, user_id, category='meds')
        elif next_stage == "shop_food":
            from handlers.inventory import show_scientist_shop
            show_scientist_shop(player, vk, user_id, category='food')
        elif next_stage == "shop_artifacts":
            show_artifacts(player, vk, user_id)
        elif next_stage in ["sell_items", "sell_gear"]:
            # Показываем инвентарь для продажи
            from handlers.inventory import show_weapons as show_inv_weapons
            show_inv_weapons(player, vk, user_id)
        return

    # Если диалог завершён
    if next_stage == "end":
        if user_id in _dialog_state:
            del _dialog_state[user_id]
        vk.messages.send(
            user_id=user_id,
            message=answer,
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    # Обычный ответ
    vk.messages.send(
        user_id=user_id,
        message=answer,
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )


# === Текстовые сообщения ===
def get_welcome_message():
    """Приветственное сообщение"""
    return (
        "ГОРОД N: ЗАПРЕТНАЯ ЗОНА\n\n"
        "Ты просыпаешься на заброшенной территории закрытого города N. "
        "Радиационный фон повышен. Инструкции в голове нет — только выживай.\n\n"
        "Используй кнопки для навигации по локациям."
    )


def get_location_description(location_id: str) -> str:
    """Получить описание локации из locations.py"""
    loc = get_location(location_id)
    if loc:
        return loc.description
    return "Неизвестная локация."


# === Обработка сообщений ===
def normalize_text(text: str) -> str:
    """Нормализация текста сообщения"""
    if not text:
        return ""
    
    text = text.strip().lower()

    return text.strip()


def handle_message(event, vk):
    """Обработка входящего сообщения"""
    import sys
    user_id = event.obj.message['from_id']
    text = normalize_text(event.obj.message.get('text', ''))
    original_text = event.obj.message.get('text', '')

    print(f"[DEBUG] START handle_message. user={user_id}, text='{text}'", file=sys.stderr)
    print(f"[DEBUG] _dialog_state={_dialog_state}", file=sys.stderr)

    player = get_player(user_id)

    # === Специальная обработка для КПП ===
    # Только если игрок НЕ в диалоге с NPC
    is_in_dialog = user_id in _dialog_state
    is_at_kpp = player.current_location_id == 'кпп' or player.previous_location == 'кпп'

    if is_at_kpp and not is_in_dialog and text in ['купить', 'оружие', 'броня']:
        if text == 'купить':
            vk.messages.send(
                user_id=user_id,
                message="🎖️ <b>Военный:</b>\n\n«Выбирай, сталкер:\n\n🔫 Оружие — от пистолетов до автоматов\n🛡️ Броня — жилеты и шлемы\n\nЦены — как есть, торга не будет.»",
                keyboard=create_kpp_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return
        elif text == 'оружие':
            from handlers.inventory import show_soldier_weapons
            show_soldier_weapons(player, vk, user_id)
            return
        elif text == 'броня':
            from handlers.inventory import show_soldier_armor
            show_soldier_armor(player, vk, user_id)
            return

    # === Проверка исследования ===
    from handlers.combat import is_researching, get_research_status, cancel_research

    if is_researching(user_id):
        # Если идёт исследование - показываем статус или обрабатываем отмену
        if text in ['отмена', 'отменить', 'стоп', 'прекратить']:
            if cancel_research(user_id):
                vk.messages.send(
                    user_id=user_id,
                    message="❌ Исследование отменено.",
                    keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                    random_id=0
                )
            return

        # Показываем статус исследования
        status = get_research_status(user_id)
        if status:
            vk.messages.send(
                user_id=user_id,
                message=(
                    f"⏳ <b>ИДЁТ ИССЛЕДОВАНИЕ</b>\n\n"
                    f"⏱️ Осталось: {status['remaining']} сек\n"
                    f"📍 Локация: {status['location_id']}\n\n"
                    f"Жди результата или напиши 'отмена' для отмены."
                ),
                random_id=0
            )
        return

    # Проверка на бой
    if user_id in _combat_state:
        print(f"[DEBUG] User {user_id} in combat. Text: '{text}'", file=sys.stderr)
        print(f"[DEBUG] Combat state: {_combat_state[user_id]}", file=sys.stderr)

        if text in ['атаковать', 'атака']:
            print(f"[DEBUG] Calling combat attack for {user_id}", file=sys.stderr)
            handle_combat_attack(player, vk, user_id)
            return
        elif text in ['убежать', 'бежать']:
            handle_combat_flee(player, vk, user_id)
            return
        elif text in ['навыки', 'навык', 'скилы', 'скилл']:
            from handlers.combat import show_skills_in_combat
            show_skills_in_combat(player, vk, user_id)
            return
        elif any(skill_name in text for skill_name in ['двойной выстрел', 'точный выстрел', 'очередь', 'подавление', 'прицельный выстрел', 'незримый', 'шквал огня', 'бронирование', 'клинок в сердце', 'уклонение', 'заградительный огонь']):
            from handlers.combat import use_skill
            original_msg = event.obj.message.get('text', '')
            use_skill(player, vk, user_id, original_msg)
            return
        elif text == 'назад':
            # Возврат в бой
            from handlers.combat import create_combat_keyboard
            vk.messages.send(
                user_id=user_id,
                message="⚔️ Возвращаемся в бой!",
                keyboard=create_combat_keyboard(player, user_id).get_keyboard(),
                random_id=0
            )
            return
        elif text in ['кпп', 'в кпп', 'выйти']:
            del _combat_state[user_id]
            go_to_location(player, 'кпп', vk, user_id)
            return
        else:
            # Если в бою, но команда не распознана - показываем клавиатуру боя
            print(f"[DEBUG] Unknown combat command: '{text}'", file=sys.stderr)
            vk.messages.send(
                user_id=user_id,
                message="⚔️ Ты в бою! Атакуй или убеги!",
                keyboard=create_combat_keyboard().get_keyboard(),
                random_id=0
            )
            return

    # Проверка на взаимодействие с аномалией
    if user_id in _anomaly_state:
        if text in ['обойти', 'извлечь', 'отступить']:
            handle_anomaly_action(player, vk, user_id, text)
            return
        else:
            vk.messages.send(
                user_id=user_id,
                message="⚠️ Ты в аномалии! Выбери действие:\n\n• Обойти — попробовать обойти\n• Извлечь — попробовать добыть артефакт\n• Отступить — уйти с уроном",
                random_id=0
            )
            return

    # === Команды ===
    
    if text in ['/start', '/help', 'начать', 'старт']:
        show_welcome(vk, user_id)
        return
    
    # === Действия в локациях (проверяем до навигации!) ===

    # Проверяем обе версии текста - нормализованную и оригинальную
    original_msg = event.obj.message.get('text', '').lower()

    if text in ['спать', 'поспать', 'отдохнуть'] or 'спать' in original_msg:
        vk.messages.send(
            user_id=user_id,
            message="Функция сна временно недоступна.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    if text in ['лечиться', 'лечение'] or 'лечиться' in original_msg or 'лечение' in original_msg:
        handle_heal(player, vk, user_id)
        return

    # Обработка "Назад" из меню статуса
    if text == '/status' or text == 'статус':
        get_status(player, vk, user_id)
        return
    
    # === Навигация ===
    
    if 'инвентарь' in text or 'инвентар' in text or 'инвентарь' in original_msg:
        go_to_inventory(player, vk, user_id)
        return
    
    if text in ['город', 'в город']:
        go_to_location(player, 'город', vk, user_id)
        return
    elif text in ['кпп', 'в кпп']:
        go_to_location(player, 'кпп', vk, user_id)
        return
    elif 'больница' in text:
        go_to_location(player, 'больница', vk, user_id)
        return
    elif 'черный рынок' in text or text == 'рынок':
        if player.level < 25:
            vk.messages.send(
                user_id=user_id,
                message="🚫 <b>Доступ запрещён!</b>\n\nЧёрный рынок открыт только для сталкеров 25+ уровня.\n\nТвоё текущее положение: {player.level} уровень\n\nПодними уровень, чтобы получить доступ.",
                random_id=0
            )
            return
        go_to_location(player, 'черный рынок', vk, user_id)
        return
    elif 'убежище' in text:
        go_to_location(player, 'убежище', vk, user_id)
        return
    elif 'военная' in text or 'дорога' in text and 'воен' in text:
        go_to_location(player, 'дорога_военная_часть', vk, user_id)
        return
    elif 'нии' in text or 'на нии' in text:
        go_to_location(player, 'дорога_нии', vk, user_id)
        return
    elif 'лес' in text or 'заражен' in text:
        go_to_location(player, 'дорога_зараженный_лес', vk, user_id)
        return
    
    if text in ['назад', 'выйти', 'выйти из']:
        go_back(player, vk, user_id)
        return
    
    # === Диалоги с NPC ===

    print(f"[DEBUG] Проверка диалога. user={user_id}, text='{text}', _dialog_state={_dialog_state}", file=sys.stderr)

    # Проверяем, находимся ли мы в диалоге с NPC
    if user_id in _dialog_state:
        dialog_info = _dialog_state[user_id]
        npc_id = dialog_info.get("npc")

        # Если игрок нажал кнопку меню (Купить, Оружие, Броня и т.д.) - сразу обрабатываем
        if npc_id == "военный" and text in ["купить", "оружие", "броня"]:
            if text == "купить":
                # Обновляем состояние диалога
                _dialog_state[user_id] = {"npc": npc_id, "stage": "shop_menu"}
                # Показываем меню магазина
                vk.messages.send(
                    user_id=user_id,
                    message="🎖️ <b>Военный:</b>\n\n«Выбирай, сталкер:\n\n🔫 Оружие — от пистолетов до автоматов\n🛡️ Броня — жилеты и шлемы\n\nЦены — как есть, торга не будет.»",
                    keyboard=create_kpp_shop_keyboard().get_keyboard(),
                    random_id=0
                )
                return
            elif text == "оружие":
                _dialog_state[user_id] = {"npc": npc_id, "stage": "shop_weapons"}
                from handlers.inventory import show_soldier_weapons
                show_soldier_weapons(player, vk, user_id)
                return
            elif text == "броня":
                _dialog_state[user_id] = {"npc": npc_id, "stage": "shop_armor"}
                from handlers.inventory import show_soldier_armor
                show_soldier_armor(player, vk, user_id)
                return

        # Магазин у учёного
        if npc_id == "ученый" and text in ["купить", "лекарства", "энергетики"]:
            if text == "купить":
                _dialog_state[user_id] = {"npc": npc_id, "stage": "shop_menu"}
                from handlers.inventory import show_scientist_shop
                show_scientist_shop(player, vk, user_id, category='all')
                return
            elif text == "лекарства":
                _dialog_state[user_id] = {"npc": npc_id, "stage": "shop_meds"}
                from handlers.inventory import show_scientist_shop
                show_scientist_shop(player, vk, user_id, category='meds')
                return
            elif text == "энергетики":
                _dialog_state[user_id] = {"npc": npc_id, "stage": "shop_food"}
                from handlers.inventory import show_scientist_shop
                show_scientist_shop(player, vk, user_id, category='food')
                return
        dialog_info = _dialog_state[user_id]
        npc_id = dialog_info.get("npc")

        # Обработка "Назад" из диалога
        if text == 'назад' or text == 'к выбору npc':
            if user_id in _dialog_state:
                # Очищаем кэш магазина при выходе
                from handlers.inventory import clear_shop_cache
                clear_shop_cache(user_id)
                del _dialog_state[user_id]
            # Возвращаемся к выбору NPC
            location_id = player.current_location_id
            npcs = get_npc_by_location(location_id)
            if npcs:
                npc_names = ", ".join([npc.name for npc in npcs])
                vk.messages.send(
                    user_id=user_id,
                    message=f"👥 <b>Выбери, с кем поговорить:</b>\n\n{npc_names}",
                    keyboard=create_npc_select_keyboard(location_id).get_keyboard(),
                    random_id=0
                )
            else:
                vk.messages.send(user_id=user_id, message="😶 Здесь никого нет для разговора.", random_id=0)
            return

        # Обработка выбора конкретного вопроса диалога
        npc = get_npc(npc_id)
        print(f"[DEBUG] Проверка меню. text='{text}', npc={npc_id}", file=sys.stderr)
        if npc:
            menu = npc.get_menu()
            print(f"[DEBUG] menu={menu}", file=sys.stderr)
            for dialog_id in menu:
                question = npc.get_question_text(dialog_id)
                print(f"[DEBUG] dialog_id='{dialog_id}', question='{question}', match={text == question.lower() or text == dialog_id}", file=sys.stderr)
                if question and (text == question.lower() or text == dialog_id):
                    show_npc_dialog(player, vk, user_id, npc_id, dialog_id)
                    return

        # Обработка "Назад" из магазина у военного
        if npc_id == "военный" and text == "назад":
            # Очищаем кэш магазина
            from handlers.inventory import clear_shop_cache
            clear_shop_cache(user_id)
            # Возвращаемся к меню военного
            show_npc_dialog(player, vk, user_id, npc_id, None)
            return

        # Обработка "Назад" из магазина у учёного
        if npc_id == "ученый" and text == "назад":
            # Очищаем кэш магазина и возвращаемся к меню
            from handlers.inventory import clear_shop_cache, show_scientist_shop
            clear_shop_cache(user_id)
            # Проверяем, из какой категории возвращаемся
            stage = _dialog_state.get(user_id, {}).get("stage", "")
            if stage in ["shop_meds", "shop_food"]:
                # Возвращаемся к меню выбора
                show_scientist_shop(player, vk, user_id, category='all')
            else:
                show_npc_dialog(player, vk, user_id, npc_id, None)
            return

        # Если ввели что-то другое в диалоге - показываем текущее меню
        show_npc_dialog(player, vk, user_id, npc_id, None)
        return

    # Начало диалога - выбор NPC
    if text in ['поговорить', 'диалог']:
        location_id = player.current_location_id
        npcs = get_npc_by_location(location_id)

        if npcs:
            npc_names = ", ".join([npc.name for npc in npcs])
            vk.messages.send(
                user_id=user_id,
                message=f"👥 <b>Выбери, с кем поговорить:</b>\n\n{npc_names}",
                keyboard=create_npc_select_keyboard(location_id).get_keyboard(),
                random_id=0
            )
            return
        elif location_id == 'убежище':
            # Для убежища используем местный житель
            show_npc_dialog(player, vk, user_id, 'местный житель')
            return
        else:
            vk.messages.send(user_id=user_id, message="😶 Здесь никого нет для разговора.", random_id=0)
            return

    # Обработка выбора конкретного NPC
    if text == 'военный':
        show_npc_dialog(player, vk, user_id, 'военный')
        return
    elif text == 'учёный' or text == 'ученый':
        show_npc_dialog(player, vk, user_id, 'ученый')
        return
    elif text == 'барыга':
        show_npc_dialog(player, vk, user_id, 'барыга')
        return
    elif text == 'местный житель':
        show_npc_dialog(player, vk, user_id, 'местный житель')
        return
    elif text == 'наставник':
        show_npc_dialog(player, vk, user_id, 'наставник')
        return

    if text in ['торговля', 'торг', 'магазин', 'торговля']:
        if player.current_location_id == 'кпп':
            vk.messages.send(
                user_id=user_id,
                message="👤 <b>Военный:</b>\n\n«Я тут не для торговли, сталкер. Военный склад охраняю. Но... если очень нужно, могу кое-что продать из трофеев. За особую цену.»",
                random_id=0
            )
            return
        elif player.current_location_id == 'черный рынок':
            vk.messages.send(
                user_id=user_id,
                message="👤 <b>Торговец:</b>\n\n«Рад тебя видеть! Вот, выбирай:\n\n🔫 Оружие\n🛡️ Броня\n🎒 Рюкзаки\n🔮 Артефакты\n💊 Медицина\n📦 Ресурсы»",
                keyboard=create_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return
        else:
            vk.messages.send(user_id=user_id, message="😶 Здесь нет торговца.", random_id=0)
            return

    # === Действия в локациях ===
    
    # Не обрабатываем как общую команду, если игрок в диалоге с NPC
    in_dialog = user_id in _dialog_state

    if text == 'купить' and not in_dialog:
        vk.messages.send(
            user_id=user_id,
            message="💰 Чтобы купить предмет, напиши 'купить <название предмета>'.\n\nПример: купить нож",
            random_id=0
        )
        return

    if text == 'продать' and not in_dialog:
        vk.messages.send(
            user_id=user_id,
            message="💵 Чтобы продать предмет, напиши 'продать <название предмета>'.\n\nПример: продать нож",
            random_id=0
        )
        return

    if 'исследовать' in text or text == 'исследовать':
        if player.current_location_id in RESEARCH_LOCATIONS:
            from handlers.combat import handle_explore_time
            handle_explore_time(player, vk, user_id)  # Без указания времени - выбирается случайно
        else:
            vk.messages.send(
                user_id=user_id,
                message="Исследование доступно только на локациях Зоны.\nСначала дойди до КПП, а оттуда — на дорогу.",
                random_id=0
            )
        return

    # === Инвентарь ===
    
    if player.current_location_id == "инвентарь":
        if text == 'назад':
            # Возвращаемся в предыдущую локацию
            prev_loc = player.previous_location or 'кпп'
            go_to_location(player, prev_loc, vk, user_id)
            return

        if text.isdigit() and 1 <= int(text) <= 9:
            if handle_inventory_digit(player, text, vk, user_id):
                return
        
        if 'оружие' in text and not in_dialog:
            show_weapons(player, vk, user_id)
            return
        elif 'броня' in text and not in_dialog:
            show_armor(player, vk, user_id)
            return
        elif 'рюкзаки' in text and not in_dialog:
            show_backpacks(player, vk, user_id)
            return
        elif 'артефакты' in text and not in_dialog:
            show_artifacts(player, vk, user_id)
            return
        elif 'ресурсы' in text and not in_dialog:
            from handlers.inventory import show_resources_shop
            show_resources_shop(player, vk, user_id)
            return
        elif 'другое' in text and not in_dialog:
            show_other(player, vk, user_id)
            return
        elif 'все' in text and not in_dialog:
            from handlers.inventory import show_all
            show_all(player, vk, user_id)
            return
        elif 'экипировка' in text and not in_dialog:
            show_equipped_artifacts(player, vk, user_id)
            return
        elif 'слоты' in text and not in_dialog:
            show_artifact_slots(player, vk, user_id)
            return
        elif 'инструкция' in text and not in_dialog:
            show_artifact_help(player, vk, user_id)
            return
    
    # === Работа с предметами ===
    
    if text.startswith('использовать ') or text.startswith('выпить ') or text.startswith('съесть '):
        if text.startswith('использовать '):
            item_name = text.replace('использовать ', '')
        elif text.startswith('выпить '):
            item_name = text.replace('выпить ', '')
        else:
            item_name = text.replace('съесть ', '')
        handle_use_item(player, item_name, vk, user_id)
        return
    
    if text.startswith('купить '):
        item_name = text.replace('купить ', '')

        if item_name in ['слот', 'слот артефакта']:
            handle_buy_artifact_slot(player, vk, user_id)
            return

        # Попытка купить по номеру
        if item_name.isdigit():
            item_num = int(item_name)
            # Проверяем, в каком магазине находится игрок
            if user_id in _dialog_state:
                dialog_info = _dialog_state[user_id]
                stage = dialog_info.get("stage", "")

                if stage == "shop_weapons":
                    from handlers.inventory import _get_shop_items_by_number
                    item_name = _get_shop_items_by_number(user_id, 'weapons', item_num)
                    if item_name:
                        handle_buy_item(player, item_name, vk, user_id)
                    else:
                        vk.messages.send(user_id=user_id, message="Нет предмета с таким номером.", random_id=0)
                    return
                elif stage == "shop_armor":
                    from handlers.inventory import _get_shop_items_by_number
                    item_name = _get_shop_items_by_number(user_id, 'armor', item_num)
                    if item_name:
                        handle_buy_item(player, item_name, vk, user_id)
                    else:
                        vk.messages.send(user_id=user_id, message="Нет предмета с таким номером.", random_id=0)
                    return

        handle_buy_item(player, item_name, vk, user_id)
        return
    
    if text.startswith('продать '):
        item_name = text.replace('продать ', '')
        handle_sell_item(player, item_name, vk, user_id)
        return
    
    if text.startswith('надеть '):
        item_name = text.replace('надеть ', '').strip()
        if not item_name:
            vk.messages.send(
                user_id=user_id,
                message="Напиши 'надеть <название предмета>'.\n\nПримеры:\n• надеть ПМ\n• надеть кожаная куртка\n• надеть рюкзак",
                random_id=0
            )
            return

        # Проверяем, что за предмет: рюкзак, оружие или броня
        player.inventory.reload()

        # Проверяем рюкзаки
        backpack = next((b for b in player.inventory.backpacks if b['name'].lower() == item_name.lower()), None)
        if backpack:
            success, msg = player.equip_backpack(backpack['name'])
            vk.messages.send(user_id=user_id, message=msg, random_id=0)
            return

        # Проверяем оружие
        weapon = next((w for w in player.inventory.weapons if w['name'].lower() == item_name.lower()), None)
        if weapon:
            success, msg = player.equip_weapon(weapon['name'])
            vk.messages.send(user_id=user_id, message=msg, random_id=0)
            return

        # Проверяем броню
        armor = next((a for a in player.inventory.armor if a['name'].lower() == item_name.lower()), None)
        if armor:
            success, msg = player.equip_armor(armor['name'])
            vk.messages.send(user_id=user_id, message=msg, random_id=0)
            return

        # Проверяем устройства (детекторы)
        device = next((d for d in player.inventory.other if d['name'].lower() == item_name.lower()), None)
        if device:
            success, msg = player.equip_device(device['name'])
            vk.messages.send(user_id=user_id, message=msg, random_id=0)
            return

        vk.messages.send(user_id=user_id, message=f"У тебя нет предмета '{item_name}' в инвентаре.", random_id=0)
        return
    
    if text == 'снять рюкзак':
        handle_unequip_backpack(player, vk, user_id)
        return

    if text == 'снять оружие':
        success, msg = player.equip_weapon()
        vk.messages.send(user_id=user_id, message=msg, random_id=0)
        return

    if text == 'снять броню':
        success, msg = player.equip_armor()
        vk.messages.send(user_id=user_id, message=msg, random_id=0)
        return

    if text == 'снять устройство' or text == 'снять детектор':
        success, msg = player.equip_device()
        vk.messages.send(user_id=user_id, message=msg, random_id=0)
        return

    if text == 'снять':
        # Показываем что можно снять
        msg = "Что снять?\n\n"
        if player.equipped_weapon:
            msg += f"• Оружие: {player.equipped_weapon} (напиши 'снять оружие')\n"
        if player.equipped_armor:
            msg += f"• Броня: {player.equipped_armor} (напиши 'снять броню')\n"
        if player.equipped_backpack:
            msg += f"• Рюкзак: {player.equipped_backpack} (напиши 'снять рюкзак')\n"
        if player.equipped_device:
            msg += f"• Устройство: {player.equipped_device} (напиши 'снять устройство')\n"

        if not player.equipped_weapon and not player.equipped_armor and not player.equipped_backpack and not player.equipped_device:
            msg = "У тебя ничего не надето."

        vk.messages.send(user_id=user_id, message=msg, random_id=0)
        return

    # === Неизвестная команда ===
    
    vk.messages.send(
        user_id=user_id,
        message="Неизвестная команда. Используй кнопки или напиши 'начать'.",
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


# === Главная функция ===
def main():
    """Запуск бота"""
    global TOKEN, GROUP_ID
    
    logger.debug(f"TOKEN: {TOKEN[:20] if TOKEN else 'EMPTY'}")
    logger.debug(f"GROUP_ID: {GROUP_ID}")

    if not TOKEN or not GROUP_ID:
        logger.error("TOKEN or GROUP_ID not found in config.py")
        return
    
    logger.info("Starting VK S.T.A.L.K.E.R. bot...")

    # Инициализация БД
    logger.info("Инициализация базы данных...")
    database.init_db()

    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)
    
    logger.info("Bot started and ready!")

    processed_events = set()
    MAX_PROCESSED = 1000
    
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            if event.obj.message.get('from_me'):
                continue
            
            event_id = event.obj.message.get('event_id')
            if event_id and event_id in processed_events:
                continue
            
            if event_id:
                processed_events.add(event_id)
                if len(processed_events) > MAX_PROCESSED:
                    processed_events.clear()
            
            try:
                handle_message(event, vk)
            except Exception as e:
                logger.error(f"Ошибка при обработке сообщения: {e}")
                user_id = event.obj.message.get('from_id', 0)
                if user_id:
                    try:
                        vk.messages.send(
                            user_id=user_id,
                            message="⚠️ Произошла ошибка. Попробуй еще раз.",
                            random_id=0
                        )
                    except:
                        pass


if __name__ == '__main__':
    main()
