"""
Модуль диалогов с NPC
"""
import database
import player as player_module
from player import invalidate_player_cache, get_player as get_player_from_module

from npcs import get_npc
from handlers.keyboards import (
    create_location_keyboard, 
    create_npc_dialog_keyboard,
    create_npc_select_keyboard,
    create_kpp_shop_keyboard
)
from handlers.inventory import (
    show_soldier_weapons, 
    show_soldier_armor,
    show_scientist_shop,
    show_artifacts,
    show_weapons,
    clear_shop_cache
)


# === Константы ===
CLASS_CHANGE_COST = 500000  # Цена смены класса


def show_npc_dialog(player, vk, user_id: int, npc_id: str, dialog_id: str = None):
    """Показать диалог с NPC"""
    from state_manager import get_dialog_info, set_dialog_state, clear_dialog_state

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
        from handlers.quests import track_quest_talk_npc
        track_quest_talk_npc(user_id)
        set_dialog_state(user_id, npc_id, "menu")
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

    # Обработка специальных диалогов
    result = _handle_special_dialog(
        player, vk, user_id, npc_id, dialog_id, answer, next_stage
    )
    if result:
        return

    # Обработка перехода в магазин
    if next_stage in ["shop_menu", "shop_weapons", "shop_armor", "shop_meds", "shop_artifacts", "sell_items", "sell_gear", "buy_artifacts"]:
        _handle_shop_redirect(player, vk, user_id, npc_id, next_stage)
        return

    # Обработка завершения диалога
    if next_stage == "end":
        clear_dialog_state(user_id)
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


def _handle_special_dialog(player, vk, user_id: int, npc_id: str, dialog_id: str, answer: str, next_stage: str):
    """Обработка специальных диалогов (набор, класс, смена класса)"""
    from classes import get_class_by_weapon, format_class_info, format_passive_status
    from state_manager import clear_dialog_state

    # Обработка набора новичка
    if dialog_id == "набор":
        result = database.give_newbie_kit(user_id)
        clear_dialog_state(user_id)

        if result is None or not result.get("success", False):
            vk.messages.send(
                user_id=user_id,
                message="👴 Местный житель:\n\n«Эй, я уже давал тебе набор! Не жадничай, сталкер. Иди в Зону — там добудешь всё сам.»",
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
        else:
            invalidate_player_cache(user_id)
            player = get_player_from_module(user_id)
            player.inventory.reload()

            # Безопасное получение списка предметов
            items = result.get("items", [])
            if items:
                items_list = "\n".join([f"• {name} x{qty}" for name, qty in items])
            else:
                items_list = "• Предметы выданы (список недоступен)"

            vk.messages.send(
                user_id=user_id,
                message=f"{answer}\n\n📦Получено:\n{items_list}\n\n💰 Деньги: 10000 руб.",
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
        return True

    # Обработка получения класса персонажа
    if dialog_id == "get_class":
        return _handle_get_class(player, vk, user_id, npc_id)

    # Обработка смены класса
    if dialog_id == "change_class":
        return _handle_change_class(player, vk, user_id, npc_id)

    # Обработка просмотра своего класса
    if dialog_id == "my_class":
        return _handle_show_class(player, vk, user_id, npc_id)

    return False


def _handle_get_class(player, vk, user_id: int, npc_id: str):
    """Обработка получения класса"""
    from classes import get_class_by_weapon, format_class_info
    from state_manager import clear_dialog_state

    if player.level < 10:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Ты ещё слишком слаб, сталкер. Приходи, когда достигнешь 10 уровня. К тому времени я посмотрю, на что ты способен.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    if not player.equipped_weapon:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«У тебя нет оружия! Как ты собираешься выживать в Зоне? Экипируй оружие и приходи снова.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    class_id = get_class_by_weapon(player.equipped_weapon)
    if not class_id:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Хм, это оружие мне не знакомо. Приходи с другим — я посмотрю, какой стиль боя тебе подходит.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    # Если класс уже есть - проверяем деньги на смену
    if player.player_class and player.player_class != class_id:
        if player.money < CLASS_CHANGE_COST:
            vk.messages.send(
                user_id=user_id,
                message=f"🎓Наставник:\n\n«Ты уже имеешь класс, но хочешь сменить на {class_id.upper()}. Это стоит {CLASS_CHANGE_COST:,} руб.\n\nУ тебя недостаточно денег — нужно ещё {CLASS_CHANGE_COST - player.money:,} руб.»",
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0
            )
            return True

        new_money = player.money - CLASS_CHANGE_COST
        database.update_user_stats(user_id, money=new_money, player_class=class_id)
        invalidate_player_cache(user_id)
        player = get_player_from_module(user_id)

        class_info = format_class_info(class_id)
        vk.messages.send(
            user_id=user_id,
            message=f"💰Наставник:\n\n«Переобучение прошло успешно! Списано {CLASS_CHANGE_COST:,} руб.\n\nТеперь ты — {class_id.split()[0]} {class_id.upper()}.\n\n{class_info}\n\n'Запомни: сила класса — в оружии. Меняй оружие — меняется и класс!'»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    # Если класса ещё нет - просто выдаём
    database.update_user_stats(user_id, player_class=class_id)
    from handlers.quests import track_quest_change_class
    track_quest_change_class(user_id)
    invalidate_player_cache(user_id)
    player = get_player_from_module(user_id)

    class_info = format_class_info(class_id)
    vk.messages.send(
        user_id=user_id,
        message=f"🎓Наставник:\n\n«Отлично! Теперь ты — {class_id.split()[0]} {class_id.upper()}. Вот твои навыки:\n\n{class_info}\n\n'Запомни: сила класса — в оружии. Меняй оружие — меняется и класс!'»",
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_change_class(player, vk, user_id: int, npc_id: str):
    """Обработка смены класса"""
    from classes import get_class_by_weapon, format_class_info
    from state_manager import clear_dialog_state

    if player.level < 10:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Ты ещё слишком слаб для смены класса. Приходи на 10 уровне.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    if not player.equipped_weapon:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Экипируй оружие, на которое хочешь перейти, и приходи снова.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    new_class_id = get_class_by_weapon(player.equipped_weapon)
    if not new_class_id:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«Это оружие мне не знакомо. Приходи с другим.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    if new_class_id == player.player_class:
        vk.messages.send(
            user_id=user_id,
            message=f"🎓Наставник:\n\n«У тебя уже есть класс {player.player_class.upper()}. Экипируй другое оружие для смены.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    if player.money < CLASS_CHANGE_COST:
        vk.messages.send(
            user_id=user_id,
            message=f"🎓Наставник:\n\n«Смена класса на {new_class_id.upper()} стоит {CLASS_CHANGE_COST:,} руб.\n\nУ тебя есть {player.money:,} руб. Не хватает {CLASS_CHANGE_COST - player.money:,} руб.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    new_money = player.money - CLASS_CHANGE_COST
    database.update_user_stats(user_id, money=new_money, player_class=new_class_id)
    from handlers.quests import track_quest_change_class
    track_quest_change_class(user_id)
    invalidate_player_cache(user_id)
    player = get_player_from_module(user_id)

    class_info = format_class_info(new_class_id)
    vk.messages.send(
        user_id=user_id,
        message=f"💰Наставник:\n\n«Класс успешно сменён! Списано {CLASS_CHANGE_COST:,} руб.\n\nТеперь ты — {new_class_id.split()[0]} {new_class_id.upper()}.\n\n{class_info}\n\n'Запомни: сила класса — в оружии!'»",
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_show_class(player, vk, user_id: int, npc_id: str):
    """Обработка просмотра класса"""
    from classes import get_class_by_weapon, format_class_info, format_passive_status

    if not player.player_class:
        vk.messages.send(
            user_id=user_id,
            message="🎓Наставник:\n\n«У тебя ещё нет класса! Приходи, когда достигнешь 10 уровня и экипируй оружие. Я обучу тебя боевому стилю.»",
            keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
            random_id=0
        )
        return True

    class_info = format_class_info(player.player_class, player.level)
    current_weapon = player.equipped_weapon or "нет"
    current_class = get_class_by_weapon(current_weapon) if current_weapon != "нет" else None

    msg = f"🎓Наставник:\n\n"
    msg += f"📌Твой текущий класс: {player.player_class.upper()}\n"
    msg += f"🔫Экипированное оружие: {current_weapon}\n"
    msg += f"⭐Твой уровень: {player.level}\n\n"

    if current_class and current_class != player.player_class:
        msg += f"⚠️Внимание! Твой экипированный класс: {current_class.upper()}\n"
        msg += "Класс меняется в зависимости от оружия!\n\n"

    passive_status = format_passive_status(player.player_class, player.level)
    msg += f"{passive_status}\n"
    msg += f"<b>Информация о классе:\n{class_info}"

    vk.messages.send(
        user_id=user_id,
        message=msg,
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_shop_redirect(player, vk, user_id: int, npc_id: str, next_stage: str):
    """Перенаправление в магазин"""
    from state_manager import set_dialog_state

    set_dialog_state(user_id, npc_id, next_stage)

    if next_stage == "shop_menu":
        vk.messages.send(
            user_id=user_id,
            message="🎖️Военный:\n\n«Выбирай, сталкер:\n\n🔫 Оружие — от пистолетов до автоматов\n🛡️ Броня — жилеты и шлемы\n\nЦены — как есть, торга не будет.»",
            keyboard=create_kpp_shop_keyboard().get_keyboard(),
            random_id=0
        )
    elif next_stage == "shop_weapons":
        show_soldier_weapons(player, vk, user_id)
    elif next_stage == "shop_armor":
        show_soldier_armor(player, vk, user_id)
    elif next_stage == "shop_meds":
        show_scientist_shop(player, vk, user_id, category='meds')
    elif next_stage == "shop_food":
        show_scientist_shop(player, vk, user_id, category='food')
    elif next_stage == "shop_artifacts":
        show_artifacts(player, vk, user_id)
    elif next_stage in ["sell_items", "sell_gear"]:
        show_weapons(player, vk, user_id)
    elif next_stage == "buy_artifacts":
        # Магазин артефактов у Барыги
        from handlers.inventory import show_artifact_shop

        set_dialog_state(user_id, npc_id, "buy_artifacts")
        show_artifact_shop(player, vk, user_id)
    elif next_stage == "sell_artifacts":
        # Продажа артефактов Барыге
        from handlers.inventory import show_sell_artifacts
        set_dialog_state(user_id, npc_id, "sell_artifacts")
        show_sell_artifacts(player, vk, user_id)


def handle_npc_choice(player, vk, user_id: int, npc_id: str):
    """Обработка выбора NPC для разговора"""
    show_npc_dialog(player, vk, user_id, npc_id, None)


def handle_npc_back(player, vk, user_id: int):
    """Обработка возврата из диалога с NPC"""
    from state_manager import clear_dialog_state, get_dialog_info
    from npcs import get_npc_by_location

    clear_dialog_state(user_id)
    clear_shop_cache(user_id)

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
    else:
        vk.messages.send(user_id=user_id, message="😶 Здесь никого нет для разговора.", random_id=0)
