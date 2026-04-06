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
DEBUG_TOKEN = os.getenv('VK_TOKEN', 'NOT_FOUND')
DEBUG_GROUP = os.getenv('GROUP_ID', 'NOT_FOUND')
logger.debug(f"After load_dotenv: TOKEN={DEBUG_TOKEN[:20] if DEBUG_TOKEN != 'NOT_FOUND' else 'NOT_FOUND'}, GROUP={DEBUG_GROUP}")

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
from handlers.combat import handle_explore, handle_combat_attack, handle_combat_flee, _combat_state as combat_state_module
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

    # Проверяем, не является ли ответ специальной командой (магазин/продажа)
    if next_stage in ["shop_weapons", "shop_meds", "shop_artifacts", "sell_items", "sell_gear"]:
        _dialog_state[user_id] = {"npc": npc_id, "stage": next_stage}
        # Перенаправляем в магазин
        if next_stage == "shop_weapons":
            show_weapons(player, vk, user_id)
        elif next_stage == "shop_meds":
            from handlers.inventory import show_other  # Медикаменты и еда в "другое"
            show_other(player, vk, user_id)
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
    user_id = event.obj.message['from_id']
    text = normalize_text(event.obj.message.get('text', ''))
    original_text = event.obj.message.get('text', '')

    # ОТЛАДКА
    import sys
    print(f"[DEBUG] Получено сообщение. user={user_id}, text='{text}', original='{original_text}'", file=sys.stderr)
    print(f"[DEBUG] _menu_state={_menu_state}", file=sys.stderr)

    player = get_player(user_id)
    
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
        elif text in ['кпп', 'в кпп', 'назад', 'выйти']:
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

    # Проверяем, находимся ли мы в диалоге с NPC
    if user_id in _dialog_state:
        dialog_info = _dialog_state[user_id]
        npc_id = dialog_info.get("npc")

        # Обработка "Назад" из диалога
        if text == 'назад' or text == 'к выбору npc':
            if user_id in _dialog_state:
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
        if npc:
            menu = npc.get_menu()
            for dialog_id in menu:
                question = npc.get_question_text(dialog_id)
                if question and (text == question.lower() or text == dialog_id):
                    show_npc_dialog(player, vk, user_id, npc_id, dialog_id)
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
                message="👤 <b>Торговец:</b>\n\n«Рад тебя видеть! Вот, выбирай:\n\n🔫 Оружие\n🛡️ Броня\n🎒 Рюкзаки\n🔮 Артефакты\n💊 Медицина»",
                keyboard=create_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return
        else:
            vk.messages.send(user_id=user_id, message="😶 Здесь нет торговца.", random_id=0)
            return

    # === Действия в локациях ===
    
    if text == 'купить':
        vk.messages.send(
            user_id=user_id,
            message="💰 Чтобы купить предмет, напиши 'купить <название предмета>'.\n\nПример: купить нож",
            random_id=0
        )
        return

    if text == 'продать':
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
        
        if 'оружие' in text:
            show_weapons(player, vk, user_id)
            return
        elif 'броня' in text:
            show_armor(player, vk, user_id)
            return
        elif 'рюкзаки' in text:
            show_backpacks(player, vk, user_id)
            return
        elif 'артефакты' in text:
            show_artifacts(player, vk, user_id)
            return
        elif 'другое' in text:
            show_other(player, vk, user_id)
            return
        elif 'все' in text:
            from handlers.inventory import show_all
            show_all(player, vk, user_id)
            return
        elif 'экипировка' in text:
            show_equipped_artifacts(player, vk, user_id)
            return
        elif 'слоты' in text:
            show_artifact_slots(player, vk, user_id)
            return
        elif 'инструкция' in text:
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
        else:
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

    if text == 'снять':
        # Показываем что можно снять
        msg = "Что снять?\n\n"
        if player.equipped_weapon:
            msg += f"• Оружие: {player.equipped_weapon} (напиши 'снять оружие')\n"
        if player.equipped_armor:
            msg += f"• Броня: {player.equipped_armor} (напиши 'снять броню')\n"
        if player.equipped_backpack:
            msg += f"• Рюкзак: {player.equipped_backpack} (напиши 'снять рюкзак')\n"

        if not player.equipped_weapon and not player.equipped_armor and not player.equipped_backpack:
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
