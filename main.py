"""
VK S.T.A.L.K.E.R. Бот - Главный файл
"""
from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
import traceback

import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

from infra import config
from infra import database
from infra import vk_messages
from models import player as player_module

# Настройка логирования
logging.basicConfig(
    level=logging.INFO if not config.DEBUG else logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# === Настройки VK ===
TOKEN = config.VK_TOKEN
GROUP_ID = config.GROUP_ID

# === Выброс (Emission) ===
from game.emission import emission_tick, schedule_next_emission
from game.limited_events import limited_events_tick

# === Импорт обработчиков ===
from handlers.commands import (
    handle_start_command,
    handle_status_command,
    handle_inventory_command,
    handle_navigation,
    handle_location_actions,
    handle_combat_commands,
    handle_research_commands,
    handle_anomaly_commands,
    handle_talk_command,
    handle_npc_selection,
    handle_trade_commands,
    handle_kpp_shop_commands,
    handle_blackmarket_commands,
    handle_dialog_commands,
    handle_buy_sell_commands,
    handle_class_commands,
    handle_unknown_command,
    normalize_text,
    get_welcome_message,
)

from handlers.location import go_to_location, go_back, handle_travel_commands, travel_tick
from handlers.map_screen import handle_map_command, show_map
from handlers.admin import handle_admin_commands
from infra.state_manager import (
    is_in_combat, is_in_dialog,
    get_combat_data, clear_combat_state,
    get_dialog_info,
    cache_player, get_cached_player,
    is_researching, cancel_research, get_research_status,
    is_in_anomaly,
    has_pending_purchase,
    has_pending_loot_choice, get_pending_loot_choice, clear_pending_loot_choice,
    has_pending_emission_risk_exit,
    has_travel_state, get_all_travel_states, clear_travel_state,
    get_ui_current_screen, set_ui_screen,
    ensure_runtime_state_loaded, hydrate_travel_states_from_runtime,
    cleanup_inactive_states,
)
from handlers.keyboards import (
    create_main_keyboard,
    create_location_keyboard,
    create_resume_keyboard,
    create_character_keyboard,
    create_inventory_keyboard,
    create_shop_keyboard,
    create_kpp_shop_keyboard,
    create_scientist_shop_keyboard,
    create_blackmarket_keyboard,
    create_artifact_shop_keyboard,
)

_user_locks = {}
_user_locks_guard = threading.Lock()
_state_cleanup_lock = threading.Lock()
_last_state_cleanup_ts = 0.0
_STATE_CLEANUP_INTERVAL_SEC = 60
_SHELTER_REGEN_TS_FLAG = "shelter_energy_regen_ts"
_SHELTER_REGEN_ACTIVE_FLAG = "shelter_energy_regen_active"


def _maybe_cleanup_inactive_states():
    """Периодическая очистка runtime-состояний с троттлингом."""
    global _last_state_cleanup_ts

    now = time.monotonic()
    if (now - _last_state_cleanup_ts) < _STATE_CLEANUP_INTERVAL_SEC:
        return

    with _state_cleanup_lock:
        now = time.monotonic()
        if (now - _last_state_cleanup_ts) < _STATE_CLEANUP_INTERVAL_SEC:
            return
        removed = cleanup_inactive_states(max_idle_seconds=300)
        _last_state_cleanup_ts = now
        if removed:
            logger.debug("cleanup_inactive_states: removed=%s", removed)


def _set_shelter_regen_anchor(user_id: int, in_shelter: bool, now_ts: int | None = None):
    """Обновить якорь времени для пассивного регена энергии в убежище."""
    if now_ts is None:
        now_ts = int(time.time())
    database.set_user_flag(user_id, _SHELTER_REGEN_TS_FLAG, int(now_ts))
    database.set_user_flag(user_id, _SHELTER_REGEN_ACTIVE_FLAG, 1 if in_shelter else 0)


def _apply_shelter_passive_energy_regen(player, user_id: int):
    """
    Применить пассивный реген энергии, если игрок находится в убежище.
    Реген учитывает только время, проведённое в убежище.
    """
    if not getattr(config, "SHELTER_PASSIVE_ENERGY_REGEN_ENABLED", True):
        return

    now_ts = int(time.time())
    in_shelter = player.current_location_id == "убежище"
    last_ts = int(database.get_user_flag(user_id, _SHELTER_REGEN_TS_FLAG, 0) or 0)
    was_shelter = int(database.get_user_flag(user_id, _SHELTER_REGEN_ACTIVE_FLAG, 0) or 0)

    if not in_shelter:
        # При выходе из убежища сбрасываем активный режим регена.
        # Повторно в БД не пишем, чтобы не нагружать запросами каждый апдейт.
        if was_shelter != 0:
            _set_shelter_regen_anchor(user_id, in_shelter=False, now_ts=now_ts)
        return

    if was_shelter != 1 or last_ts <= 0 or now_ts <= last_ts:
        _set_shelter_regen_anchor(user_id, in_shelter=True, now_ts=now_ts)
        return

    if int(player.energy) >= 100:
        # На полном заряде не накапливаем будущий реген.
        if last_ts != now_ts:
            database.set_user_flag(user_id, _SHELTER_REGEN_TS_FLAG, now_ts)
        return

    interval = max(30, int(getattr(config, "SHELTER_PASSIVE_ENERGY_REGEN_INTERVAL_SEC", 300) or 300))
    amount = max(1, int(getattr(config, "SHELTER_PASSIVE_ENERGY_REGEN_AMOUNT", 1) or 1))
    elapsed = now_ts - last_ts
    ticks = elapsed // interval
    if ticks <= 0:
        return

    old_energy = int(player.energy)
    gained = int(ticks * amount)
    new_energy = min(100, old_energy + gained)

    if new_energy > old_energy:
        player.energy = new_energy
        database.update_user_stats(user_id, energy=new_energy)

    # Сохраняем остаток времени до следующего тика; при полном заряде якорь сбрасываем на now.
    new_anchor = now_ts if new_energy >= 100 else int(last_ts + ticks * interval)
    if new_anchor != last_ts:
        database.set_user_flag(user_id, _SHELTER_REGEN_TS_FLAG, new_anchor)


def _get_user_lock(user_id: int) -> threading.Lock:
    """Получить lock пользователя для последовательной обработки его апдейтов."""
    with _user_locks_guard:
        lock = _user_locks.get(user_id)
        if lock is None:
            lock = threading.Lock()
            _user_locks[user_id] = lock
        return lock


def get_player(user_id: int):
    """Получить игрока (из кэша или создать)"""
    if config.ENABLE_PLAYER_CACHE:
        player = get_cached_player(user_id)
        if player:
            return player

    player = player_module.Player(user_id)
    if config.ENABLE_PLAYER_CACHE:
        cache_player(user_id, player)
    return player


def handle_message(event, vk):
    """Обработка входящего сообщения"""
    user_id = event.obj.message['from_id']
    text = normalize_text(event.obj.message.get('text', ''))
    original_text = event.obj.message.get('text', '')

    # Получаем игрока
    player = get_player(user_id)
    ensure_runtime_state_loaded(user_id)
    try:
        _apply_shelter_passive_energy_regen(player, user_id)
    except Exception:
        logger.exception("Ошибка пассивного регена энергии (user_id=%s)", user_id)

    # Админские команды доступны в любой локации/состоянии
    if handle_admin_commands(player, vk, user_id, text, original_text):
        return

    # Бан пользователя
    if player.is_banned:
        reason = player.ban_reason or "не указана"
        vk.messages.send(
            user_id=user_id,
            message=f"⛔ Ты заблокирован администратором.\nПричина: {reason}",
            random_id=0,
        )
        return

    # Проверяем состояния
    in_combat = is_in_combat(user_id)
    in_dialog = is_in_dialog(user_id)

    # === Приоритет 1: Бой ===
    if in_combat:
        if handle_combat_commands(player, vk, user_id, text, original_text):
            return

    # === Приоритет 1.5: Кнопки выброса (impact) даже без pending ===
    try:
        from game.emission import handle_emission_impact_actions
        if handle_emission_impact_actions(player, vk, user_id, text):
            return
    except Exception:
        logger.exception("Ошибка роутинга impact-кнопок (user_id=%s)", user_id)

    # === Приоритет 2: Аномалия ===
    if handle_anomaly_commands(player, vk, user_id, text):
        return

    # === Приоритет 3: Исследование ===
    if handle_research_commands(player, vk, user_id, text):
        return

    # === Приоритет 3.5: Подтверждение покупки P2P (если есть pending) ===
    if has_pending_purchase(user_id):
        from handlers.market import handle_market_confirm_purchase
        if handle_market_confirm_purchase(player, vk, user_id, text):
            return

    # === Приоритет 3.55: Выбор найденного лута (аномалия) ===
    if has_pending_loot_choice(user_id):
        if _handle_pending_loot_choice(player, vk, user_id, text):
            return

    # === Приоритет 3.6: Случайное событие / предупреждение выброса ===
    from handlers.events import handle_event_response
    if handle_event_response(player, vk, user_id, text):
        return

    # === Приоритет 3.65: Подтверждение выхода из safe во время impact ===
    if has_pending_emission_risk_exit(user_id):
        from game.emission import handle_emission_risk_exit_response
        if handle_emission_risk_exit_response(player, vk, user_id, text):
            return

    # === Приоритет 3.7: Коридор перемещения ===
    if has_travel_state(user_id):
        if handle_travel_commands(player, vk, user_id, text):
            return

    # === Приоритет 4: Команда /start ===
    if text in ['/start', '/help', 'начать', 'старт']:
        handle_start_command(vk, user_id)
        return

    # === Приоритет 4.5: Экран персонажа ===
    if text in ['персонаж', 'перс', 'меню персонажа']:
        if player.current_location_id == "инвентарь":
            vk.messages.send(
                user_id=user_id,
                message="Сначала выйди из инвентаря кнопкой 'Назад'.",
                keyboard=create_inventory_keyboard().get_keyboard(),
                random_id=0
            )
            return
        current_ui = get_ui_current_screen(user_id)
        push_current = current_ui.get("name") != "character"
        set_ui_screen(user_id, {"name": "character"}, push_current=push_current)
        vk.messages.send(
            user_id=user_id,
            message="👤 ПЕРСОНАЖ\nВыбери раздел:",
            keyboard=create_character_keyboard().get_keyboard(),
            random_id=0
        )
        return

    # === Приоритет 4.6: Карта маршрутов ===
    if handle_map_command(player, vk, user_id, text):
        return

    ui_screen = get_ui_current_screen(user_id).get("name", "location")

    # В экране "Персонаж" разрешаем только разделы персонажа и "Назад"
    if ui_screen == "character":
        if text in ['назад', '⬅️ назад', 'back', 'выйти']:
            go_back(player, vk, user_id)
            return
        if text in ['/status', 'статус']:
            vk.messages.send(
                user_id=user_id,
                message=player.get_status(),
                keyboard=create_character_keyboard().get_keyboard(),
                random_id=0
            )
            return
        if 'инвентарь' in text or 'инвентар' in text:
            handle_inventory_command(player, vk, user_id)
            return
        from handlers.commands import handle_quests_commands
        if handle_quests_commands(player, vk, user_id, text):
            return
        vk.messages.send(
            user_id=user_id,
            message="В меню 'Персонаж' доступны: Статус, Инвентарь, Задания и Назад.",
            keyboard=create_character_keyboard().get_keyboard(),
            random_id=0
        )
        return

    if ui_screen == "inventory":
        blocked_in_inventory = {
            'город', 'в город', 'кпп', 'в кпп', 'больница',
            'убежище', 'черный рынок', 'рынок', 'поговорить',
            'торговля', 'торг', 'магазин', 'лечиться', 'лечение',
        }
        if text in blocked_in_inventory or text.startswith('дорога '):
            vk.messages.send(
                user_id=user_id,
                message="Нельзя прыгать в другие разделы из инвентаря. Сначала нажми 'Назад'.",
                keyboard=create_inventory_keyboard().get_keyboard(),
                random_id=0
            )
            return

    # === Приоритет 5: КПП магазин (без диалога) ===
    if not in_dialog and handle_kpp_shop_commands(player, vk, user_id, text):
        return

    # === Приоритет 6: Диалог с NPC ===
    if in_dialog:
        if handle_dialog_commands(player, vk, user_id, text, original_text):
            return

    # === Приоритет 7: Стандартные команды ===

    # Статус
    if text == '/status' or text == 'статус':
        vk.messages.send(
            user_id=user_id,
            message="Открой раздел 'Персонаж' и выбери 'Статус'.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0
        )
        return
    
    # Класс персонажа
    if text in ['класс', 'мой класс', 'получить класс', 'мои навыки', 'навыки']:
        from handlers.commands import handle_class_commands
        handle_class_commands(player, vk, user_id, text)
        return

    # Инвентарь
    if 'инвентарь' in text or 'инвентар' in text:
        vk.messages.send(
            user_id=user_id,
            message="Открой раздел 'Персонаж' и выбери 'Инвентарь'.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0
        )
        return
    
    # Назад (возврат в предыдущую локацию) — НО не из инвентаря (там свой обработчик)
    if text in ['назад', '⬅️ назад', 'назад в город', 'назад⬅️', 'back']:
        go_back(player, vk, user_id)
        return

    # Действия в локации (лечение)
    if handle_location_actions(player, vk, user_id, text):
        return

    # Навигация
    if handle_navigation(player, vk, user_id, text):
        return

    # Разговор с NPC
    if handle_talk_command(player, vk, user_id, text):
        return

    # Выбор NPC
    if handle_npc_selection(player, vk, user_id, text):
        return

    # Торговля
    if handle_trade_commands(player, vk, user_id, text):
        return

    # Черный рынок (артефакты)
    if handle_blackmarket_commands(player, vk, user_id, text):
        return

    # Покупка/продажа
    if handle_buy_sell_commands(player, vk, user_id, text, in_dialog):
        return

    # Ежедневные задания
    from handlers.commands import handle_quests_commands
    quest_words = ("задания", "ежедневные задания", "квесты", "daily", "/daily", "задания показать", "квесты показать")
    if text in quest_words:
        vk.messages.send(
            user_id=user_id,
            message="Открой раздел 'Персонаж' и выбери 'Задания'.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0
        )
        return
    if handle_quests_commands(player, vk, user_id, text):
        return

    # === Работа с предметами (через player) ===
    if _handle_item_commands(player, vk, user_id, text):
        return

    # === Неизвестная команда ===
    handle_unknown_command(vk, user_id)


def _handle_item_commands(player, vk, user_id: int, text: str) -> bool:
    """Обработка команд работы с предметами"""
    from handlers.inventory import (
        handle_inventory_digit, handle_use_item,
        handle_buy_item, handle_sell_item,
        handle_buy_artifact_slot,
        handle_inspect_item,
        handle_unequip_backpack, handle_drop_item, handle_drop_item_by_index,
        handle_sell_item_by_number,
        show_weapons, show_armor, show_backpacks,
        show_artifacts, show_other, show_resources_shop,
        show_all, show_equipped_artifacts,
        show_artifact_slots, show_artifact_help,
    )
    from handlers.combat import handle_explore_time
    from game.constants import RESEARCH_LOCATIONS

    # Исследование
    if 'исследовать' in text:
        if player.current_location_id in RESEARCH_LOCATIONS:
            handle_explore_time(player, vk, user_id)
        else:
            vk.messages.send(
                user_id=user_id,
                message="Исследование доступно только на локациях Зоны.",
                random_id=0
            )
        return True

    # Инвентарь - цифры
    if player.current_location_id == "инвентарь":
        if text == 'назад':
            go_back(player, vk, user_id)
            return True

        # Категории инвентаря в режиме инвентаря
        if 'оружие' in text:
            show_weapons(player, vk, user_id)
            return True
        elif 'броня' in text:
            show_armor(player, vk, user_id)
            return True
        elif 'рюкзаки' in text:
            show_backpacks(player, vk, user_id)
            return True
        elif 'артефакты' in text:
            show_artifacts(player, vk, user_id)
            return True
        elif 'другое' in text:
            show_other(player, vk, user_id)
            return True
        elif 'все' in text:
            show_all(player, vk, user_id)
            return True

        # Цифры для выбора предмета (поддерживаем 1-99)
        if text.isdigit() and 1 <= int(text) <= 99:
            if handle_inventory_digit(player, text, vk, user_id):
                return True

    # Использовать предмет
    if text.startswith(('использовать ', 'выпить ', 'съесть ')):
        if text.startswith('использовать '):
            item_name = text.replace('использовать ', '')
        elif text.startswith('выпить '):
            item_name = text.replace('выпить ', '')
        else:
            item_name = text.replace('съесть ', '')
        handle_use_item(player, item_name, vk, user_id)
        return True

    # Осмотреть предмет
    if text.startswith('осмотреть '):
        target = text.replace('осмотреть ', '', 1).strip()
        if not target:
            vk.messages.send(
                user_id=user_id,
                message="Напиши: осмотреть <номер|название предмета>",
                random_id=0
            )
            return True
        handle_inspect_item(player, target, vk, user_id)
        return True

    # Купить предмет — только на КПП или Черном рынке
    if text.startswith('купить '):
        dialog_info = get_dialog_info(user_id) or {}
        trader_context = (
            player.current_location_id == 'черный рынок'
            or dialog_info.get("npc") == "барыга"
        )
        if not trader_context:
            vk.messages.send(
                user_id=user_id,
                message="🕴️ Купить можно только у Барыги.",
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
            return True

        item_name = text.replace('купить ', '')

        if item_name in ['слот', 'слот артефакта']:
            handle_buy_artifact_slot(player, vk, user_id)
            return True

        # Покупка по номеру
        if item_name.isdigit():
            if _handle_shop_buy_by_number(player, vk, user_id, item_name):
                return True

        # Покупка по названию из текущей витрины Барыги.
        from handlers.inventory import get_shop_cache_data
        shop_data = get_shop_cache_data(user_id)
        if 'trader_all' not in shop_data and 'artifacts' not in shop_data:
            vk.messages.send(
                user_id=user_id,
                message="❌ Сначала открой витрину Барыги, затем покупай.",
                random_id=0
            )
            return True

        handle_buy_item(player, item_name, vk, user_id)
        return True

    # Продать предмет — только на КПП или Черном рынке
    if text.startswith('продать '):
        dialog_info = get_dialog_info(user_id) or {}
        trader_context = (
            player.current_location_id == 'черный рынок'
            or dialog_info.get("npc") == "барыга"
        )
        if not trader_context:
            vk.messages.send(
                user_id=user_id,
                message="🕴️ Продать можно только Барыге.",
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
            return True

        item_name = text.replace('продать ', '')

        # Продажа артефактов по номеру
        from handlers.inventory import get_shop_cache_data
        shop_data = get_shop_cache_data(user_id)
        if 'sell_all' in shop_data and item_name.isdigit():
            if handle_sell_item_by_number(player, vk, user_id, item_name):
                return True

        if 'sell_artifacts' in shop_data and item_name.isdigit():
            from handlers.inventory import handle_sell_artifact_by_number
            if handle_sell_artifact_by_number(player, vk, user_id, item_name):
                return True

        # Продажа артефактов по названию
        if 'sell_artifacts' in shop_data:
            from handlers.inventory import handle_sell_artifact
            handle_sell_artifact(player, item_name, vk, user_id)
            return True

        handle_sell_item(player, item_name, vk, user_id)
        return True

    # Надеть предмет
    if text.startswith('надеть '):
        item_name = text.replace('надеть ', '').strip()
        if not item_name:
            vk.messages.send(
                user_id=user_id,
                message="Напиши 'надеть <название предмета>'.\n\nПримеры:\n• надеть ПМ\n• надеть кожаная куртка",
                random_id=0
            )
            return True

        player.inventory.reload()

        # Рюкзак
        backpack = next((b for b in player.inventory.backpacks if b['name'].lower() == item_name.lower()), None)
        if backpack:
            success, msg = player.equip_backpack(backpack['name'])
            vk.messages.send(user_id=user_id, message=msg, random_id=0)
            return True

        # Оружие
        weapon = next((w for w in player.inventory.weapons if w['name'].lower() == item_name.lower()), None)
        if weapon:
            success, msg = player.equip_weapon(weapon['name'])
            vk.messages.send(user_id=user_id, message=msg, random_id=0)
            return True

        # Броня
        armor = next((a for a in player.inventory.armor if a['name'].lower() == item_name.lower()), None)
        if armor:
            success, msg = player.equip_armor(armor['name'])
            vk.messages.send(user_id=user_id, message=msg, random_id=0)
            return True

        # Устройство
        device = next((d for d in player.inventory.other if d['name'].lower() == item_name.lower()), None)
        if device:
            success, msg = player.equip_device(device['name'])
            vk.messages.send(user_id=user_id, message=msg, random_id=0)
            return True

        vk.messages.send(user_id=user_id, message=f"У тебя нет предмета '{item_name}' в инвентаре.", random_id=0)
        return True

    if text.startswith('улучшить оружие') or text.startswith('прокачать оружие'):
        item_name = text.replace('улучшить оружие', '').replace('прокачать оружие', '').strip()
        success, msg = player.upgrade_weapon(item_name or None)
        vk.messages.send(user_id=user_id, message=msg, random_id=0)
        return True

    # Снять предмет
    if text in ['снять рюкзак', 'снять оружие', 'снять броню', 'снять устройство', 'снять детектор', 'снять']:
        if text == 'снять рюкзак':
            handle_unequip_backpack(player, vk, user_id)
            return True
        elif text == 'снять оружие':
            success, msg = player.equip_weapon()
            vk.messages.send(user_id=user_id, message=msg, random_id=0)
            return True
        elif text == 'снять броню':
            success, msg = player.equip_armor()
            vk.messages.send(user_id=user_id, message=msg, random_id=0)
            return True
        elif text in ['снять устройство', 'снять детектор']:
            success, msg = player.equip_device()
            vk.messages.send(user_id=user_id, message=msg, random_id=0)
            return True
        elif text == 'снять':
            msg = _get_unequip_list(player)
            vk.messages.send(user_id=user_id, message=msg, random_id=0)
            return True

    # Выбросить предмет
    if text.startswith('выбросить '):
        item_name = text.replace('выбросить ', '').strip()

        # Если указана цифра - выбрасываем по номеру в текущем разделе
        if item_name.isdigit():
            handle_drop_item_by_index(player, int(item_name), vk, user_id)
        else:
            handle_drop_item(player, item_name, vk, user_id)
        return True

    return False


def _handle_pending_loot_choice(player, vk, user_id: int, text: str) -> bool:
    """Обработка выбора: оставить или выбросить найденный предмет."""
    choice = text.strip().lower()
    if choice not in {"оставить", "выбросить"}:
        vk.messages.send(
            user_id=user_id,
            message="Найден предмет. Выбери: 'Оставить' или 'Выбросить'.",
            random_id=0
        )
        return True

    data = get_pending_loot_choice(user_id)
    if not data:
        return False

    item_name = data.get("item_name")
    location_id = data.get("location_id", player.current_location_id)
    shells_after = data.get("shells_after")
    item_type = data.get("item_type", "предмет")
    clear_pending_loot_choice(user_id)

    if not item_name:
        vk.messages.send(
            user_id=user_id,
            message="Выбор устарел. Продолжай исследование.",
            keyboard=create_resume_keyboard(location_id, player.level, user_id).get_keyboard(),
            random_id=0
        )
        return True

    if choice == "оставить":
        database.add_item_to_inventory(user_id, item_name, 1)
        if item_type == "artifact":
            from handlers.quests import track_quest_artifact
            track_quest_artifact(user_id, vk=vk)
        remain_part = f"\nГильз осталось: {shells_after}" if shells_after is not None else ""
        vk.messages.send(
            user_id=user_id,
            message=f"✅ {item_name} добавлен в инвентарь.{remain_part}",
            keyboard=create_resume_keyboard(location_id, player.level, user_id).get_keyboard(),
            random_id=0
        )
        return True

    remain_part = f"\nГильз осталось: {shells_after}" if shells_after is not None else ""
    vk.messages.send(
        user_id=user_id,
        message=f"🗑️ Ты выбросил {item_name}.{remain_part}",
        keyboard=create_resume_keyboard(location_id, player.level, user_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_shop_buy_by_number(player, vk, user_id: int, item_num: str) -> bool:
    """Обработка покупки по номеру в магазине"""
    from handlers.inventory import _get_shop_items_by_number, get_shop_cache_data, handle_buy_item

    dialog_info = get_dialog_info(user_id)
    try:
        num = int(item_num)
    except ValueError:
        return False

    if not dialog_info:
        # Вне диалога покупка по номеру должна работать для всех витрин.
        shop_data = get_shop_cache_data(user_id)

        item_name = _get_shop_items_by_number(user_id, 'trader_all', num)
        if item_name:
            handle_buy_item(player, item_name, vk, user_id)
            return True

        item_name = _get_shop_items_by_number(user_id, 'weapons', num)
        if item_name:
            handle_buy_item(player, item_name, vk, user_id)
            return True

        item_name = _get_shop_items_by_number(user_id, 'armor', num)
        if item_name:
            handle_buy_item(player, item_name, vk, user_id)
            return True

        item_name = _get_shop_items_by_number(user_id, 'scientist', num)
        if item_name:
            handle_buy_item(player, item_name, vk, user_id)
            return True

        if 'artifacts' in shop_data:
            return _handle_buy_artifact_by_number(player, vk, user_id, item_num)

        return False

    stage = dialog_info.get("stage", "")

    if stage == "shop_weapons":
        item_name = _get_shop_items_by_number(user_id, 'weapons', num)
        if item_name:
            handle_buy_item(player, item_name, vk, user_id)
            return True
        else:
            vk.messages.send(user_id=user_id, message="Нет предмета с таким номером.", random_id=0)
            return True
    elif stage == "shop_armor":
        item_name = _get_shop_items_by_number(user_id, 'armor', num)
        if item_name:
            handle_buy_item(player, item_name, vk, user_id)
            return True
        else:
            vk.messages.send(user_id=user_id, message="Нет предмета с таким номером.", random_id=0)
            return True
    elif stage in {"buy_all", "buy_artifacts"}:
        item_name = _get_shop_items_by_number(user_id, 'trader_all', num)
        if item_name:
            handle_buy_item(player, item_name, vk, user_id)
            return True
        else:
            vk.messages.send(user_id=user_id, message="Нет предмета с таким номером.", random_id=0)
            return True

    # Обработка покупки артефактов по названию
    shop_data = get_shop_cache_data(user_id)
    if 'artifacts' in shop_data:
        return _handle_buy_artifact_by_number(player, vk, user_id, item_num)

    return False


def _handle_buy_artifact_by_number(player, vk, user_id: int, item_num: str) -> bool:
    """Обработка покупки артефакта по номеру"""
    from handlers.inventory import get_shop_cache_data, handle_buy_artifact

    shop_data = get_shop_cache_data(user_id)
    artifacts = shop_data.get('artifacts', [])

    if not artifacts:
        return False

    try:
        idx = int(item_num) - 1
        if 0 <= idx < len(artifacts):
            artifact = artifacts[idx]
            item_name = artifact['name']
            return handle_buy_artifact(player, item_name, vk, user_id)
        else:
            vk.messages.send(user_id=user_id, message="Нет артефакта с таким номером.", random_id=0)
            return True
    except ValueError:
        return False


def _get_unequip_list(player) -> str:
    """Получить список надетых предметов для снятия"""
    msg = "Что снять?\n\n"

    if player.equipped_weapon:
        msg += f"• Оружие: {player.equipped_weapon} (напиши 'снять оружие')\n"

    equipped_armor = [
        getattr(player, "equipped_armor", None),
        getattr(player, "equipped_armor_head", None),
        getattr(player, "equipped_armor_body", None),
        getattr(player, "equipped_armor_legs", None),
        getattr(player, "equipped_armor_hands", None),
        getattr(player, "equipped_armor_feet", None),
    ]
    armor_names = [name for idx, name in enumerate(equipped_armor) if name and name not in equipped_armor[:idx]]
    if armor_names:
        msg += f"• Броня: {', '.join(armor_names)} (напиши 'снять броню')\n"

    if player.equipped_backpack:
        msg += f"• Рюкзак: {player.equipped_backpack} (напиши 'снять рюкзак')\n"
    if player.equipped_device:
        msg += f"• Устройство: {player.equipped_device} (напиши 'снять устройство')\n"

    if not any([player.equipped_weapon, armor_names,
                player.equipped_backpack, player.equipped_device]):
        msg = "У тебя ничего не надето."

    return msg


def _handle_message_error(event, vk, error: Exception):
    logger.error(f"Ошибка при обработке сообщения: {error}")
    traceback.print_exc()

    user_id = event.obj.message.get('from_id', 0)
    if user_id:
        try:
            vk.messages.send(
                user_id=user_id,
                message="⚠️ Произошла ошибка. Попробуй еще раз.",
                random_id=0
            )
        except Exception:
            pass


def _process_message_event(event, vk):
    _maybe_cleanup_inactive_states()
    user_id = event.obj.message.get('from_id', 0)
    if not user_id:
        return

    lock = _get_user_lock(user_id)
    with lock:
        try:
            handle_message(event, vk)
        except Exception as e:
            _handle_message_error(event, vk, e)


def _process_callback_event(event, vk):
    _maybe_cleanup_inactive_states()
    user_id = getattr(event.obj, "user_id", 0)
    lock = _get_user_lock(user_id) if user_id else None

    try:
        if lock:
            with lock:
                _do_callback_processing(event, vk)
        else:
            _do_callback_processing(event, vk)
    except Exception:
        logger.exception("Ошибка обработки callback-события")
        try:
            vk_messages.answer_event(
                vk,
                event_id=event.obj.event_id,
                user_id=event.obj.user_id,
                peer_id=event.obj.peer_id,
                text="Ошибка действия",
                show_snackbar=True,
            )
        except Exception:
            logger.exception("Не удалось ответить на callback после ошибки")


def _answer_callback(event, vk, text: str):
    """Быстро закрыть loading-состояние callback-кнопки."""
    return vk_messages.answer_event(
        vk,
        event_id=event.obj.event_id,
        user_id=event.obj.user_id,
        peer_id=event.obj.peer_id,
        text=text,
        show_snackbar=True,
    )


def _do_callback_processing(event, vk):
    """Основная логика обработки callback-события."""
    payload = event.obj.payload or {}
    user_id = getattr(event.obj, "user_id", 0)

    if payload.get("command") == "map":
        region = payload.get("region")
        if region == "overview":
            region = None
        _answer_callback(event, vk, "Карта обновлена")
        player = get_player(user_id)
        show_map(player, vk, user_id, region)
        return

    if payload.get("command") == "inventory_section":
        section = payload.get("section")
        player = get_player(user_id)
        if player.current_location_id != "инвентарь":
            _answer_callback(event, vk, "Сначала открой инвентарь")
            return

        from handlers.inventory import (
            show_all,
            show_armor,
            show_artifacts,
            show_backpacks,
            show_other,
            show_weapons,
        )

        section_handlers = {
            "weapons": show_weapons,
            "armor": show_armor,
            "backpacks": show_backpacks,
            "artifacts": show_artifacts,
            "other": show_other,
            "all": show_all,
        }
        handler = section_handlers.get(section)
        if not handler:
            _answer_callback(event, vk, "Раздел устарел")
            return

        _answer_callback(event, vk, "Инвентарь обновлен")
        handler(player, vk, user_id)
        return

    if payload.get("command") == "inventory_back":
        _answer_callback(event, vk, "Возврат")
        player = get_player(user_id)
        go_back(player, vk, user_id)
        return

    if payload.get("command") == "back":
        _answer_callback(event, vk, "Возврат")
        player = get_player(user_id)
        try:
            _apply_shelter_passive_energy_regen(player, user_id)
        except Exception:
            logger.exception("Ошибка пассивного регена энергии в callback (user_id=%s)", user_id)
        return_location = payload.get("location") or player.previous_location or 'город'

        vk_messages.send(
            vk,
            user_id=user_id,
            message=f"↩️ Возвращаемся в {return_location}...",
            keyboard=create_location_keyboard(return_location, player.level).get_keyboard(),
        )

        player.current_location_id = return_location
        database.update_user_location(user_id, return_location)
        _set_shelter_regen_anchor(user_id, in_shelter=(return_location == "убежище"))
        return

    _answer_callback(event, vk, "Действие устарело")


def _event_worker(task_queue: "queue.Queue[tuple[str, object]]", vk):
    while True:
        kind, event = task_queue.get()
        try:
            if kind == "message_new":
                _process_message_event(event, vk)
            elif kind == "message_event":
                _process_callback_event(event, vk)
        finally:
            task_queue.task_done()


# === Главная функция ===
def main():
    """Запуск бота"""
    logger.debug(f"TOKEN: {TOKEN[:20] if TOKEN else 'EMPTY'}")
    logger.debug(f"GROUP_ID: {GROUP_ID}")

    if not TOKEN or not GROUP_ID:
        logger.error("TOKEN or GROUP_ID not found in config.py")
        return
    
    logger.info("Starting VK S.T.A.L.K.E.R. bot...")

    # Инициализация БД
    logger.info("Инициализация базы данных...")
    database.init_db()
    restored_travel = hydrate_travel_states_from_runtime()
    if restored_travel:
        logger.info("Восстановлено переходов из runtime storage: %d", restored_travel)

    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)
    
    logger.info(
        "Bot started and ready! workers=%d queue_max=%d player_cache=%s db_pool=%d..%d",
        config.BOT_WORKERS,
        config.BOT_QUEUE_MAX,
        config.ENABLE_PLAYER_CACHE,
        config.DB_POOL_MIN,
        config.DB_POOL_MAX,
    )

    task_queue: "queue.Queue[tuple[str, object]]" = queue.Queue(maxsize=config.BOT_QUEUE_MAX)
    for idx in range(max(1, config.BOT_WORKERS)):
        threading.Thread(
            target=_event_worker,
            args=(task_queue, vk),
            name=f"event-worker-{idx + 1}",
            daemon=True,
        ).start()

    # === Фоновый планировщик выбросов (каждую минуту) ===
    def _emission_scheduler():
        """Фоновый поток для управления выбросами"""
        import time
        # Планируем первый выброс
        if config.EMISSION_ENABLED:
            try:
                schedule_next_emission()
            except Exception as e:
                logger.error("Ошибка начального планирования выброса: %s", e, exc_info=True)

        last_tick = time.time()
        while True:
            time.sleep(10)  # Проверяем каждые 10 секунд
            now = time.time()
            if now - last_tick >= 60:  # Но тик — раз в минуту
                last_tick = now
                try:
                    emission_tick(vk)
                except Exception as e:
                    logger.error("Ошибка в emission_tick: %s", e)

    if config.EMISSION_ENABLED:
        threading.Thread(
            target=_emission_scheduler,
            name="emission-scheduler",
            daemon=True,
        ).start()
        logger.info("Планировщик выбросов запущен")

    def _limited_events_scheduler():
        """Фоновый поток ограниченных ивентов (анонс/старт/завершение)."""
        import time
        if not config.LIMITED_EVENTS_ENABLED:
            return
        last_tick = time.time()
        while True:
            time.sleep(10)
            now = time.time()
            if now - last_tick >= 60:
                last_tick = now
                try:
                    limited_events_tick(vk)
                except Exception as e:
                    logger.error("Ошибка в limited_events_tick: %s", e, exc_info=True)

    if config.LIMITED_EVENTS_ENABLED:
        threading.Thread(
            target=_limited_events_scheduler,
            name="limited-events-scheduler",
            daemon=True,
        ).start()
        logger.info("Планировщик ограниченных ивентов запущен")

    def _travel_scheduler():
        """Фоновый поток тиков коридора перемещения."""
        import time
        fail_counts: dict[int, int] = {}
        while True:
            time.sleep(2)
            states = get_all_travel_states()
            if not states:
                continue
            for uid, _ in states:
                lock = _get_user_lock(uid)
                if not lock.acquire(blocking=False):
                    continue
                try:
                    player = get_player(uid)
                    travel_tick(player, vk, uid, silent=True)
                    fail_counts.pop(uid, None)
                except Exception as e:
                    fail_counts[uid] = fail_counts.get(uid, 0) + 1
                    logger.error(
                        "Ошибка в travel_tick(user_id=%s), попытка %d: %s",
                        uid, fail_counts[uid], e, exc_info=True
                    )
                    # Если один и тот же переход подряд падает, чтобы не зациклиться в сломанном состоянии
                    # и не спамить лог каждые 2 секунды — сбрасываем коридор.
                    if fail_counts[uid] >= 3:
                        clear_travel_state(uid)
                        fail_counts.pop(uid, None)
                        try:
                            vk.messages.send(
                                user_id=uid,
                                message="⚠️ Переход прерван из-за временной ошибки. Запусти перемещение повторно.",
                                random_id=0,
                            )
                        except Exception:
                            pass
                finally:
                    lock.release()

    threading.Thread(
        target=_travel_scheduler,
        name="travel-scheduler",
        daemon=True,
    ).start()
    logger.info("Планировщик переходов запущен")

    def _market_scheduler():
        """Фоновый поток: истечение лотов и рассылка уведомлений об истечении."""
        import time
        last_expire_tick = 0.0
        while True:
            time.sleep(10)
            now = time.time()
            try:
                # Регулярно закрываем истёкшие лоты даже без активности игроков в рынке.
                if now - last_expire_tick >= 30:
                    database.expire_market_listings(limit=300)
                    last_expire_tick = now

                # Рассылаем уведомления по истёкшим лотам без дублей.
                notifications = database.claim_expired_market_notifications(limit=120)
                for n in notifications:
                    try:
                        vk.messages.send(
                            user_id=int(n["seller_vk_id"]),
                            message=(
                                "⏰ ЛОТ ИСТЁК\n\n"
                                f"Лот #{n['id']} истёк по времени.\n"
                                f"Предмет: {n['item_name']} x{n['quantity']}\n"
                                "Предмет автоматически возвращён в инвентарь."
                            ),
                            random_id=0,
                        )
                    except Exception:
                        logger.warning(
                            "Не удалось отправить уведомление об истечении лота #%s пользователю %s",
                            n.get("id"), n.get("seller_vk_id"),
                            exc_info=True,
                        )
            except Exception as e:
                logger.error("Ошибка в market_scheduler: %s", e, exc_info=True)

    threading.Thread(
        target=_market_scheduler,
        name="market-scheduler",
        daemon=True,
    ).start()
    logger.info("Планировщик рынка запущен")

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
                task_queue.put(
                    ("message_new", event),
                    timeout=config.BOT_QUEUE_PUT_TIMEOUT,
                )
            except queue.Full:
                logger.warning("Очередь обработки заполнена, апдейт пропущен")
                user_id = event.obj.message.get('from_id', 0)
                if user_id:
                    try:
                        vk.messages.send(
                            user_id=user_id,
                            message="⏳ Бот перегружен. Попробуй через пару секунд.",
                            random_id=0,
                        )
                    except Exception:
                        pass

        elif event.type == VkBotEventType.MESSAGE_EVENT:
            try:
                task_queue.put(
                    ("message_event", event),
                    timeout=config.BOT_QUEUE_PUT_TIMEOUT,
                )
            except queue.Full:
                logger.warning("Очередь обработки заполнена, callback пропущен")


if __name__ == '__main__':
    main()
