"""
Модуль обработки команд игрока
Централизованная обработка всех команд и сообщений
"""
import sys

import player as player_module
from player import get_player as get_player_cached

from handlers.location import (
    go_to_location, go_to_inventory, go_back,
    handle_heal, get_status, show_welcome
)
from handlers.combat import (
    handle_explore, handle_combat_attack, handle_combat_flee,
    is_researching, get_research_status, cancel_research,
    show_skills_in_combat, use_skill
)
from handlers.keyboards import (
    create_location_keyboard, create_combat_keyboard,
    create_npc_select_keyboard
)
from handlers.npc import (
    show_npc_dialog, handle_npc_choice, handle_npc_back
)
from handlers.inventory import (
    show_weapons, show_armor, show_backpacks, show_artifacts, show_other,
    show_soldier_weapons, show_soldier_armor, show_scientist_shop
)
from handlers.keyboards import (
    create_location_keyboard, create_combat_keyboard,
    create_npc_select_keyboard, create_kpp_shop_keyboard,
    create_scientist_shop_keyboard
)
from npcs import get_npc_by_location
from state_manager import (
    is_in_combat,
    is_in_dialog, get_dialog_info, clear_dialog_state,
    is_researching as is_in_research,
    get_research_data, clear_research_state,
    get_research_status, cancel_research,
    is_in_anomaly, get_anomaly_data
)


# === Текстовые сообщения ===

def get_welcome_message():
    """Приветственное сообщение"""
    return (
        "ГОРОД N: ЗАПРЕТНАЯ ЗОНА\n\n"
        "Ты просыпаешься на заброшенной территории закрытого города N. "
        "Радиационный фон повышен. Инструкции в голове нет — только выживай.\n\n"
        "Используй кнопки для навигации по локациям.\n\n"
        "Подсказки:\n"
        "• Начни с КПП: там военный и учёный\n"
        "• Черный рынок откроется с 25 уровня\n"
        "• P2P рынок игроков находится внутри Черного рынка"
    )


# === Утилиты ===

def normalize_text(text: str) -> str:
    """Нормализация текста сообщения"""
    if not text:
        return ""
    return text.strip().lower().strip()


# === Обработчики команд ===

def handle_start_command(vk, user_id: int):
    """Обработка команды /start"""
    show_welcome(vk, user_id)


def handle_status_command(player, vk, user_id: int):
    """Обработка команды статус"""
    get_status(player, vk, user_id)


def handle_inventory_command(player, vk, user_id: int):
    """Обработка команды инвентарь"""
    go_to_inventory(player, vk, user_id)


def handle_navigation(player, vk, user_id: int, text: str):
    """Обработка навигационных команд"""
    current = player.current_location_id
    requested = None

    if text in ['город', 'в город']:
        requested = 'город'
    elif text in ['кпп', 'в кпп']:
        requested = 'кпп'
    elif 'больница' in text:
        requested = 'больница'
    elif 'черный рынок' in text or (text == 'рынок' and current != 'черный рынок'):
        requested = 'черный рынок'
    elif 'убежище' in text:
        requested = 'убежище'
    elif 'военная' in text or ('дорога' in text and 'воен' in text):
        requested = 'дорога_военная_часть'
    elif 'нии' in text or 'на нии' in text:
        requested = 'дорога_нии'
    elif 'лес' in text or 'заражен' in text:
        requested = 'дорога_зараженный_лес'

    if text in ['назад', 'выйти', 'выйти из']:
        go_back(player, vk, user_id)
        return True

    if not requested:
        return False

    if requested == 'черный рынок' and player.level < 25:
        vk.messages.send(
            user_id=user_id,
            message=f"🚫Доступ запрещён!\n\nЧёрный рынок открыт только для сталкеров 25+ уровня.\n\nТвоё текущее положение: {player.level} уровень\n\nПодними уровень, чтобы получить доступ.",
            random_id=0
        )
        return True

    allowed_transitions = {
        'город': {'кпп', 'больница', 'убежище', 'черный рынок'},
        'кпп': {'город', 'дорога_военная_часть', 'дорога_нии', 'дорога_зараженный_лес'},
        'убежище': {'город'},
        'больница': {'город'},
        'черный рынок': {'город'},
        'дорога_военная_часть': {'кпп'},
        'дорога_нии': {'кпп'},
        'дорога_зараженный_лес': {'кпп'},
    }

    # Из инвентаря прямые переходы запрещены, нужен "Назад"
    if current == 'инвентарь':
        vk.messages.send(
            user_id=user_id,
            message="Сначала выйди из инвентаря кнопкой 'Назад'.",
            keyboard=create_location_keyboard(current).get_keyboard(),
            random_id=0
        )
        return True

    allowed = allowed_transitions.get(current, set())
    if requested not in allowed:
        vk.messages.send(
            user_id=user_id,
            message="Переход недоступен с текущего экрана. Используй кнопки текущей локации.",
            keyboard=create_location_keyboard(current, player.level).get_keyboard(),
            random_id=0
        )
        return True

    go_to_location(player, requested, vk, user_id)
    return True


def handle_location_actions(player, vk, user_id: int, text: str):
    """Обработка действий в локации"""
    from handlers.location import handle_sleep

    # Лечение
    if text in ['лечиться', 'лечение'] or 'лечиться' in text or 'лечение' in text:
        handle_heal(player, vk, user_id)
        return True

    # Отдых в убежище
    if text in ['спать', 'сон', 'отдохнуть'] or 'спать' in text:
        handle_sleep(player, vk, user_id)
        return True
    
    return False


def handle_combat_commands(player, vk, user_id: int, text: str, original_text: str):
    """Обработка команд боя"""
    if not is_in_combat(user_id):
        return False

    # Атака
    if text in ['атаковать', 'атака']:
        handle_combat_attack(player, vk, user_id)
        return True

    # Бегство
    if text in ['убежать', 'бежать']:
        handle_combat_flee(player, vk, user_id)
        return True

    # Навыки
    if text in ['навыки', 'навык', 'скилы', 'скилл']:
        show_skills_in_combat(player, vk, user_id)
        return True

    # Боевой инвентарь (только использование предметов)
    if text in ['инвентарь', 'инвентарь в бою', 'предметы', 'рюкзак']:
        _show_combat_inventory(player, vk, user_id)
        return True

    if text.isdigit():
        if _use_combat_item_by_index(player, vk, user_id, int(text)):
            return True

    if text.startswith(('использовать ', 'выпить ', 'съесть ')):
        if text.startswith('использовать '):
            target = text.replace('использовать ', '', 1).strip()
        elif text.startswith('выпить '):
            target = text.replace('выпить ', '', 1).strip()
        else:
            target = text.replace('съесть ', '', 1).strip()
        if _use_combat_item(player, vk, user_id, target):
            return True

    # Использование навыка по имени
    skill_keywords = ['двойной выстрел', 'точный выстрел', 'очередь', 'подавление', 
                      'прицельный выстрел', 'незримый', 'шквал огня', 'бронирование', 
                      'клинок в сердце', 'уклонение', 'заградительный огонь']
    if any(skill_name in text for skill_name in skill_keywords):
        use_skill(player, vk, user_id, original_text)
        return True

    # Возврат в бой
    if text == 'назад':
        vk.messages.send(
            user_id=user_id,
            message="⚔️ Возвращаемся в бой!",
            keyboard=create_combat_keyboard().get_keyboard(),
            random_id=0
        )
        return True

    # Блок любых переходов/экранов во время боя
    blocked_texts = {
        'кпп', 'в кпп', 'город', 'в город', 'больница', 'убежище',
        'черный рынок', 'рынок', 'персонаж', 'перс', 'статус', 'задания',
        'поговорить', 'торговля', 'магазин', 'выйти',
    }
    if text in blocked_texts or text.startswith('дорога'):
        vk.messages.send(
            user_id=user_id,
            message="⚔️ Пока идёт бой, нельзя менять экран или локацию.\nДоступно: Атаковать, Навыки, Инвентарь, Убежать.",
            keyboard=create_combat_keyboard().get_keyboard(),
            random_id=0
        )
        return True

    # Неизвестная команда в бою
    vk.messages.send(
        user_id=user_id,
        message="⚔️ Ты в бою.\nДоступно: Атаковать, Навыки, Инвентарь, Убежать.",
        keyboard=create_combat_keyboard().get_keyboard(),
        random_id=0
    )
    return True


def _show_combat_inventory(player, vk, user_id: int):
    """Показать расходники, которые можно использовать прямо в бою."""
    player.inventory.reload()
    items = player.inventory.other

    if not items:
        vk.messages.send(
            user_id=user_id,
            message="🎒 В боевом кармане пусто.\nНет расходников для использования.",
            keyboard=create_combat_keyboard().get_keyboard(),
            random_id=0
        )
        return

    msg = "🎒 БОЕВОЙ ИНВЕНТАРЬ\n\n"
    for idx, item in enumerate(items, 1):
        msg += f"{idx}. {item['name']} x{item.get('quantity', 1)}\n"
    msg += "\nИспользуй: 'использовать <номер>' или 'использовать <название>'\nНазад — вернуться в бой."

    vk.messages.send(
        user_id=user_id,
        message=msg,
        keyboard=create_combat_keyboard().get_keyboard(),
        random_id=0
    )


def _use_combat_item_by_index(player, vk, user_id: int, idx: int) -> bool:
    """Использовать расходник по номеру во время боя."""
    if idx <= 0:
        return False
    player.inventory.reload()
    items = player.inventory.other
    if idx > len(items):
        vk.messages.send(
            user_id=user_id,
            message="Нет предмета с таким номером в боевом инвентаре.",
            keyboard=create_combat_keyboard().get_keyboard(),
            random_id=0
        )
        return True
    return _use_combat_item(player, vk, user_id, items[idx - 1]["name"])


def _use_combat_item(player, vk, user_id: int, target: str) -> bool:
    """Использовать предмет в бою только из секции other."""
    if not target:
        return False

    player.inventory.reload()
    item = None

    if target.isdigit():
        idx = int(target)
        if idx <= 0 or idx > len(player.inventory.other):
            vk.messages.send(
                user_id=user_id,
                message="Нет предмета с таким номером в боевом инвентаре.",
                keyboard=create_combat_keyboard().get_keyboard(),
                random_id=0
            )
            return True
        item = player.inventory.other[idx - 1]
    else:
        item = next((it for it in player.inventory.other if it["name"].lower() == target.lower()), None)

    if not item:
        vk.messages.send(
            user_id=user_id,
            message="В бою можно использовать только расходники из раздела 'Другое'.",
            keyboard=create_combat_keyboard().get_keyboard(),
            random_id=0
        )
        return True

    success, msg = player.use_item(item["name"])
    vk.messages.send(
        user_id=user_id,
        message=msg,
        keyboard=create_combat_keyboard().get_keyboard(),
        random_id=0
    )
    return True


def handle_research_commands(player, vk, user_id: int, text: str):
    """Обработка команд исследования"""
    if not is_in_research(user_id):
        return False
    
    # Отмена исследования
    if text in ['отмена', 'отменить', 'стоп', 'прекратить']:
        if cancel_research(user_id):
            vk.messages.send(
                user_id=user_id,
                message="❌ Исследование отменено.",
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
        return True
    
    # Показать статус исследования
    status = get_research_data(user_id)
    if status:
        vk.messages.send(
            user_id=user_id,
            message=(
                f"⏳ИДЁТ ИССЛЕДОВАНИЕ\n\n"
                f"⏱️ Осталось: {status.get('remaining', 0)} сек\n"
                f"📍 Локация: {status.get('location_id', 'unknown')}\n\n"
                f"Жди результата или напиши 'отмена' для отмены."
            ),
            random_id=0
        )
        return True
    
    return False


def handle_anomaly_commands(player, vk, user_id: int, text: str):
    """Обработка команд аномалии"""
    from handlers.combat import handle_anomaly_action
    
    if not is_in_anomaly(user_id):
        return False
    
    if text in ['обойти', 'извлечь', 'бросить гильзу', 'добыть', 'отступить']:
        handle_anomaly_action(player, vk, user_id, text)
        return True
    
    vk.messages.send(
        user_id=user_id,
        message="⚠️ Ты в аномалии! Выбери действие:\n\n• Обойти — попробовать обойти\n• Извлечь — попробовать добыть артефакт\n• Отступить — уйти с уроном",
        random_id=0
    )
    return True


def handle_talk_command(player, vk, user_id: int, text: str):
    """Обработка команды поговорить"""
    if text not in ['поговорить', 'диалог']:
        return False
    
    location_id = player.current_location_id
    npcs = get_npc_by_location(location_id)

    if npcs:
        npc_names = ", ".join([npc.name for npc in npcs])
        vk.messages.send(
            user_id=user_id,
            message=f"👥Выбери, с кем поговорить:\n\n{npc_names}",
            keyboard=create_npc_select_keyboard(location_id).get_keyboard(),
            random_id=0
        )
        return True
    elif location_id == 'убежище':
        show_npc_dialog(player, vk, user_id, 'местный житель')
        return True
    
    vk.messages.send(user_id=user_id, message="😶 Здесь никого нет для разговора.", random_id=0)
    return True


def handle_npc_selection(player, vk, user_id: int, text: str):
    """Обработка выбора NPC"""
    npc_map = {
        'военный': 'военный',
        'учёный': 'ученый',
        'ученый': 'ученый',
        'барыга': 'барыга',
        'местный житель': 'местный житель',
        'наставник': 'наставник',
        'медик': 'медик',
        'дозиметрист': 'дозиметрист',
    }
    
    npc_id = npc_map.get(text)
    if npc_id:
        show_npc_dialog(player, vk, user_id, npc_id)
        return True
    
    return False


def handle_class_commands(player, vk, user_id: int, text: str):
    """Обработка команд класса персонажа"""
    # Команды: класс, мой класс, получить класс
    if text not in ['класс', 'мой класс', 'получить класс', 'мои навыки', 'навыки']:
        return False

    from classes import get_class_by_weapon, format_class_info, format_passive_status
    from handlers.keyboards import create_location_keyboard

    # Если игрок в убежище - показываем через NPC
    if player.current_location_id == 'убежище':
        from handlers.npc import show_npc_dialog
        show_npc_dialog(player, vk, user_id, 'наставник')
        return True

    # Иначе показываем информацию о классе напрямую
    if not player.player_class:
        # Попробуем определить класс по оружию
        if player.equipped_weapon:
            class_id = get_class_by_weapon(player.equipped_weapon)
            if class_id:
                class_info = format_class_info(class_id, player.level)
                vk.messages.send(
                    user_id=user_id,
                    message=f"🎓Твой класс: {class_id.upper()}\n\n{class_info}\n\nДля получения класса найди наставника в убежище (дорога → убежище).",
                    keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                    random_id=0
                )
                return True

        vk.messages.send(
            user_id=user_id,
            message="🎓КЛАСС ПЕРСОНАЖА\n\nУ тебя пока нет класса!\n\nДля получения класса:\n1. Дойди до 10 уровня\n2. Экипируй оружие\n3. Найди наставника в убежище\n\n🚪 Путь: Дорога → Убежище",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return True

    # Показываем инфу о текущем классе
    class_info = format_class_info(player.player_class, player.level)
    passive_status = format_passive_status(player.player_class, player.level)

    current_weapon = player.equipped_weapon or "нет"
    current_class = get_class_by_weapon(current_weapon) if current_weapon != "нет" else None

    msg = f"🎓ТВОЙ КЛАСС\n\n"
    msg += f"Класс: {player.player_class.upper()}\n"
    msg += f"Оружие: {current_weapon}\n\n"
    msg += f"{class_info}\n"

    if passive_status:
        msg += f"\n{passive_status}"

    msg += "\n\nДля смены класса найди наставника в убежище."

    vk.messages.send(
        user_id=user_id,
        message=msg,
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )
    return True


def handle_trade_commands(player, vk, user_id: int, text: str):
    """Обработка команд торговли"""
    if text not in ['торговля', 'торг', 'магазин', 'товары', 'товары барыги', 'лавка']:
        return False
    
    location_id = player.current_location_id
    
    if location_id == 'кпп':
        vk.messages.send(
            user_id=user_id,
            message="👤Военный:\n\n«Я тут не для торговли, сталкер. Военный склад охраняю. Но... если очень нужно, могу кое-что продать из трофеев. За особую цену.»",
            random_id=0
        )
        return True
    
    if location_id == 'черный рынок':
        from handlers.keyboards import create_blackmarket_keyboard
        vk.messages.send(
            user_id=user_id,
            message=(
                "👤Торговец:\n\n«Рад тебя видеть, сталкер! Вот, выбирай:\n\n"
                "🔮 Артефакты — редкие аномальные образования\n"
                "🔫 Оружие\n"
                "🛡️ Броня\n"
                "🎒 Рюкзаки\n"
                "💰 Продать артефакты — избавься от лишнего\n"
                "📈 Рынок игроков — торговля между сталкерами через эскроу\n\n"
                "Чтобы зайти в P2P: нажми «Рынок игроков» или напиши «рынок игроков».»"
            ),
            keyboard=create_blackmarket_keyboard().get_keyboard(),
            random_id=0
        )
        return True
    
    vk.messages.send(user_id=user_id, message="😶 Здесь нет торговца.", random_id=0)
    return True


def handle_kpp_shop_commands(player, vk, user_id: int, text: str):
    """Обработка команд магазина на КПП (без диалога с NPC)"""
    if player.current_location_id != 'кпп':
        return False
    
    is_at_kpp = player.previous_location == 'кпп'
    if not is_at_kpp and player.current_location_id != 'кпп':
        return False
    
    if text in ['купить', 'оружие', 'броня', 'продать']:
        if text == 'купить':
            vk.messages.send(
                user_id=user_id,
                message="🎖️Военный:\n\n«Выбирай, сталкер:\n\n🔫 Оружие — от пистолетов до автоматов\n🛡️ Броня — жилеты и шлемы\n💰 Продать — скупка трофеев\n\nЦены — как есть, торга не будет.»",
                keyboard=create_kpp_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return True
        elif text == 'оружие':
            show_soldier_weapons(player, vk, user_id)
            return True
        elif text == 'броня':
            show_soldier_armor(player, vk, user_id)
            return True
        elif text == 'продать':
            show_weapons(player, vk, user_id)
            vk.messages.send(
                user_id=user_id,
                message="💰 Продажа военному: напиши `продать <название>` или `продать <номер>`.",
                random_id=0
            )
            return True
    
    return False


def handle_blackmarket_commands(player, vk, user_id: int, text: str):
    """Обработка команд на Черном рынке"""
    if player.current_location_id != 'черный рынок':
        return False

    from handlers.inventory import show_artifact_shop, show_sell_artifacts, show_soldier_weapons, show_soldier_armor
    from handlers.keyboards import create_blackmarket_keyboard
    from handlers.market import (
        show_market_menu,
        handle_market_input,
        handle_market_create_listing,
        handle_market_buy_listing,
        handle_market_cancel_listing,
    )

    # Универсальный обработчик рынка (пагинация, сортировка, поиск, навигация)
    if handle_market_input(player, vk, user_id, text):
        return True

    # Команды P2P рынка (парсим первыми, чтобы не перехватились обычным "купить ...")
    if handle_market_create_listing(player, vk, user_id, text):
        return True
    if handle_market_buy_listing(player, vk, user_id, text):
        return True
    if handle_market_cancel_listing(player, vk, user_id, text):
        return True

    if text in ['рынок игроков', 'барахолка']:
        show_market_menu(player, vk, user_id)
        return True

    # Артефакты - меню
    if text in ['артефакты', 'артефакт', 'артефакты купить', 'купить артефакты']:
        show_artifact_shop(player, vk, user_id, rarity=None)
        return True

    # Артефакты по редкости
    if text in ['обычные', 'обычные артефакты']:
        show_artifact_shop(player, vk, user_id, rarity='common')
        return True

    if text in ['редкие', 'редкие артефакты']:
        show_artifact_shop(player, vk, user_id, rarity='rare')
        return True

    if text in ['уникальные', 'уникальные артефакты']:
        show_artifact_shop(player, vk, user_id, rarity='unique')
        return True

    if text in ['легендарные', 'легендарные артефакты']:
        show_artifact_shop(player, vk, user_id, rarity='legendary')
        return True

    # Продажа артефактов
    if text in ['продать артефакты', 'продать артефакт', 'продажа артефактов']:
        show_sell_artifacts(player, vk, user_id)
        return True

    # Оружие и броня
    if text == 'оружие':
        show_soldier_weapons(player, vk, user_id)
        return True

    if text == 'броня':
        show_soldier_armor(player, vk, user_id)
        return True

    return False


def handle_dialog_commands(player, vk, user_id: int, text: str, original_text: str):
    """Обработка команд внутри диалога с NPC"""
    if not is_in_dialog(user_id):
        return False
    
    dialog_info = get_dialog_info(user_id)
    if not dialog_info:
        return False
    
    npc_id = dialog_info.get("npc")
    stage = dialog_info.get("stage", "")

    # В торговых стадиях NPC отдаём команды покупки/продажи в общий обработчик предметов,
    # иначе они перехватываются диалогом и не выполняются.
    shop_stages = {
        "shop_menu", "shop_weapons", "shop_armor", "shop_meds", "shop_food",
        "sell_items", "sell_gear", "buy_artifacts", "sell_artifacts"
    }
    if stage in shop_stages:
        shop_passthrough = (
            text.startswith("купить ")
            or text.startswith("продать ")
            or text.isdigit()
        )
        if shop_passthrough:
            return False

    # Отдельно оставляем passthrough для команд P2P рынка у Барыги.
    if npc_id == "барыга" and stage in {"buy_artifacts", "sell_artifacts"}:
        market_passthrough = text in {"рынок игроков", "рынок", "рынок показать", "мои лоты", "мои сделки"}
        if market_passthrough:
            return False

    # Обработка "Назад" из диалога — но НЕ из магазина (там свой обработчик)
    if text == 'к выбору npc':
        handle_npc_back(player, vk, user_id)
        return True

    if text == 'назад' and stage not in ("shop_menu", "shop_weapons", "shop_armor", "shop_meds", "shop_food", "sell_items", "sell_gear", "buy_artifacts", "sell_artifacts"):
        handle_npc_back(player, vk, user_id)
        return True
    
    # Обработка меню магазина у военного
    if npc_id == "военный" and text in ["купить", "оружие", "броня", "продать"]:
        from state_manager import set_dialog_state
        from handlers.keyboards import create_kpp_shop_keyboard
        from handlers.inventory import show_weapons
        
        if text == "купить":
            set_dialog_state(user_id, npc_id, "shop_menu")
            vk.messages.send(
                user_id=user_id,
                message="🎖️Военный:\n\n«Выбирай, сталкер:\n\n🔫 Оружие — от пистолетов до автоматов\n🛡️ Броня — жилеты и шлемы\n💰 Продать — скупка трофеев\n\nЦены — как есть, торга не будет.»",
                keyboard=create_kpp_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return True
        elif text == "оружие":
            set_dialog_state(user_id, npc_id, "shop_weapons")
            show_soldier_weapons(player, vk, user_id)
            return True
        elif text == "броня":
            set_dialog_state(user_id, npc_id, "shop_armor")
            show_soldier_armor(player, vk, user_id)
            return True
        elif text == "продать":
            set_dialog_state(user_id, npc_id, "sell_items")
            show_weapons(player, vk, user_id)
            vk.messages.send(
                user_id=user_id,
                message="💰 Продажа военному: напиши `продать <название>` или `продать <номер>`.",
                random_id=0
            )
            return True
    
    # Обработка меню магазина у учёного
    if npc_id == "ученый" and text in ["купить", "лекарства", "энергетики"]:
        from state_manager import set_dialog_state
        from handlers.keyboards import create_scientist_shop_keyboard
        
        if text == "купить":
            set_dialog_state(user_id, npc_id, "shop_menu")
            show_scientist_shop(player, vk, user_id, category='all')
            return True
        elif text == "лекарства":
            set_dialog_state(user_id, npc_id, "shop_meds")
            show_scientist_shop(player, vk, user_id, category='meds')
            return True
        elif text == "энергетики":
            set_dialog_state(user_id, npc_id, "shop_food")
            show_scientist_shop(player, vk, user_id, category='food')
            return True

    # Обработка магазина у Барыги на КПП
    if npc_id == "барыга":
        from state_manager import set_dialog_state
        from handlers.inventory import show_artifact_shop, show_sell_artifacts

        if text in ["купить", "купить артефакты", "артефакты"]:
            set_dialog_state(user_id, npc_id, "buy_artifacts")
            show_artifact_shop(player, vk, user_id, rarity=None)
            return True

        if text in ["продать", "продать артефакты", "продажа артефактов"]:
            set_dialog_state(user_id, npc_id, "sell_artifacts")
            show_sell_artifacts(player, vk, user_id)
            return True
    
    # Обработка выбора вопроса диалога
    from npcs import get_npc
    npc = get_npc(npc_id)
    if npc:
        menu = npc.get_menu()
        for dialog_id in menu:
            question = npc.get_question_text(dialog_id)
            if question and (text == question.lower() or text == dialog_id):
                show_npc_dialog(player, vk, user_id, npc_id, dialog_id)
                return True
    
    # Обработка "Назад" из магазина
    if text == "назад":
        from handlers.inventory import clear_shop_cache
        
        if npc_id == "военный":
            clear_shop_cache(user_id)
            show_npc_dialog(player, vk, user_id, npc_id, None)
            return True
        
        if npc_id == "ученый":
            clear_shop_cache(user_id)
            if stage in ["shop_meds", "shop_food"]:
                show_scientist_shop(player, vk, user_id, category='all')
            else:
                show_npc_dialog(player, vk, user_id, npc_id, None)
            return True

        # Назад от Барыги
        if npc_id == "барыга":
            clear_shop_cache(user_id)
            show_npc_dialog(player, vk, user_id, npc_id, None)
            return True

    # Обработка редкости артефактов (у Барыги или напрямую)
    rarity_map = {
        'обычные': 'common',
        'редкие': 'rare',
        'уникальные': 'unique',
        'легендарные': 'legendary'
    }

    text_lower = text.lower().strip()

    if text_lower in rarity_map:
        from handlers.inventory import show_artifact_shop
        show_artifact_shop(player, vk, user_id, rarity=rarity_map[text_lower])
        return True

    # Показать текущее меню диалога
    show_npc_dialog(player, vk, user_id, npc_id, None)
    return True


def handle_buy_sell_commands(player, vk, user_id: int, text: str, in_dialog: bool):
    """Обработка команд покупки/продажи"""
    # Если есть pending покупка на рынке — пропускаем, её обрабатывает handle_market_confirm_purchase
    from state_manager import has_pending_purchase
    if has_pending_purchase(user_id):
        return False

    if in_dialog:
        return False

    if text == 'купить':
        if player.current_location_id not in ('кпп', 'черный рынок'):
            vk.messages.send(
                user_id=user_id,
                message="⛠ Купить предметы можно только на КПП или Чёрном рынке.",
                random_id=0
            )
            return True
        vk.messages.send(
            user_id=user_id,
            message="💰 Чтобы купить предмет, напиши 'купить <название предмета>'.\n\nПример: купить нож",
            random_id=0
        )
        return True

    if text == 'продать':
        if player.current_location_id not in ('кпп', 'черный рынок'):
            vk.messages.send(
                user_id=user_id,
                message="⛠ Продать предметы можно только на КПП или Чёрном рынке.",
                random_id=0
            )
            return True
        show_weapons(player, vk, user_id)
        return True

    return False


def handle_unknown_command(vk, user_id: int):
    """Обработка неизвестной команды"""
    vk.messages.send(
        user_id=user_id,
        message="😕 Я не понимаю эту команду.\n\nИспользуй кнопки для навигации или напиши 'начать' для справки.",
        random_id=0
    )


# =========================================================================
# Ежедневные задания
# =========================================================================

def handle_quests_commands(player, vk, user_id: int, text: str) -> bool:
    """Обработка команд ежедневных заданий"""
    from handlers.quests import handle_daily_quests_command, handle_claim_rewards

    if handle_daily_quests_command(player, vk, user_id, text):
        return True
    if handle_claim_rewards(player, vk, user_id, text):
        return True
    return False
