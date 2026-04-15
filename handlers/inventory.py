"""
Обработчики инвентаря
"""
from __future__ import annotations
import threading

import database
import ui
from constants import InventorySection


def _fmt_weight(item: dict, default: float = 1.0) -> str:
    return f"{float(item.get('weight', default)):.1f}кг"


def _screen_header(title: str, player) -> str:
    return (
        f"{ui.title(title)}\n"
        f"⚖️ Вес: {player.inventory.total_weight:.1f}/{player.max_weight:.1f}кг\n"
        f"💰 Деньги: {player.money} руб.\n"
    )


def _screen_footer(action_hint: str) -> str:
    return (
        f"\n{ui.section('Действия')}\n"
        f"• Цифра: {action_hint}\n"
        "• выбросить <номер|название>\n"
        "• Назад"
    )


def handle_inventory_digit(player, text: str, vk, user_id: int) -> bool:
    """Обработка цифр 1-99 в инвентаре. Возвращает True если обработано."""
    from main import create_inventory_keyboard
    
    if not text.isdigit() or not (1 <= int(text) <= 99):
        return False
    
    section = player.inventory_section
    item_num = int(text) - 1  # 0-based для списка
    
    if not section:
        return False
    
    handlers = {
        'weapons': _equip_weapon,
        'armor': _equip_armor,
        'backpacks': _equip_backpack,
        'other': _use_item,
    }
    
    handler = handlers.get(section)
    if handler:
        return handler(player, item_num, vk, user_id)
    
    # Артефакты - особая логика
    if section == 'artifacts':
        return _handle_artifact_digit(player, item_num, vk, user_id)
    
    return False


def _equip_weapon(player, index: int, vk, user_id: int) -> bool:
    from main import create_inventory_keyboard
    
    player.inventory.reload()
    weapons = player.inventory.weapons
    
    if index >= len(weapons):
        vk.messages.send(user_id=user_id, message="Нет оружия с таким номером.", random_id=0)
        return True
    
    weapon = weapons[index]
    weapon_name = weapon['name']
    
    player.equipped_weapon = weapon_name
    database.update_user_stats(user_id, equipped_weapon=weapon_name)
    
    vk.messages.send(user_id=user_id, message=f"Надето оружие: {weapon_name}!", random_id=0)
    return True


def _equip_armor(player, index: int, vk, user_id: int) -> bool:
    from main import create_inventory_keyboard
    
    player.inventory.reload()
    armor_items = player.inventory.armor
    
    if index >= len(armor_items):
        vk.messages.send(user_id=user_id, message="Нет брони с таким номером.", random_id=0)
        return True
    
    armor = armor_items[index]
    armor_name = armor['name']

    # Используем функцию игрока для правильного определения типа брони
    success, msg = player.equip_armor(armor_name)

    vk.messages.send(
        user_id=user_id,
        message=msg,
        random_id=0
    )
    return True


def _equip_backpack(player, index: int, vk, user_id: int) -> bool:
    from main import create_inventory_keyboard
    
    player.inventory.reload()
    backpacks = player.inventory.backpacks
    
    if index >= len(backpacks):
        vk.messages.send(user_id=user_id, message="Нет рюкзака с таким номером.", random_id=0)
        return True
    
    backpack = backpacks[index]
    backpack_name = backpack['name']
    
    success, msg = player.equip_backpack(backpack_name)
    vk.messages.send(user_id=user_id, message=msg, random_id=0)
    return True


def _use_item(player, index: int, vk, user_id: int) -> bool:
    from main import create_location_keyboard
    
    player.inventory.reload()
    other_items = player.inventory.other
    
    if index >= len(other_items):
        vk.messages.send(user_id=user_id, message="Нет предмета с таким номером.", random_id=0)
        return True
    
    item = other_items[index]
    item_name = item['name']

    # Проверяем, не детектор ли это
    if 'детектор' in item_name.lower():
        success, msg = player.equip_device(item_name)
        vk.messages.send(
            user_id=user_id,
            message=msg,
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return True

    success, msg = player.use_item(item_name)
    vk.messages.send(
        user_id=user_id,
        message=msg,
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )
    return True


def _handle_artifact_digit(player, index: int, vk, user_id: int) -> bool:
    """Обработка артефактов по цифрам"""
    from main import create_inventory_keyboard
    
    player.inventory.reload()
    artifacts = player.inventory.artifacts
    equipped = player.equipped_artifacts
    
    # Нумерация: экипированные (1,2,3...) + в инвентаре (4,5,6...)
    total_count = len(equipped) + len(artifacts)
    
    if index >= total_count:
        vk.messages.send(user_id=user_id, message="Нет артефакта с таким номером.", random_id=0)
        return True
    
    if index < len(equipped):
        # Снять экипированный артефакт
        artifact_name = equipped[index]
        result = database.unequip_artifact(user_id, artifact_name)
        
        if result['success']:
            player._artifact_bonuses = player._get_artifact_bonuses()
            player.max_health_bonus = player._artifact_bonuses.get('max_health_bonus', 0)
            if player.health > player.max_health:
                player.health = player.max_health
                database.update_user_stats(user_id, health=player.health)
            player.inventory.reload()
            msg = f"Артефакт {artifact_name} снят!"
        else:
            msg = f"{result['message']}"

        vk.messages.send(user_id=user_id, message=msg, random_id=0)
    else:
        # Экипировать артефакт из инвентаря
        artifact_idx = index - len(equipped)
        artifact_name = artifacts[artifact_idx]['name']
        result = database.equip_artifact(user_id, artifact_name)
        
        if result['success']:
            player._artifact_bonuses = player._get_artifact_bonuses()
            player.max_health_bonus = player._artifact_bonuses.get('max_health_bonus', 0)
            if player.health > player.max_health:
                player.health = player.max_health
                database.update_user_stats(user_id, health=player.health)
            player.inventory.reload()
            msg = f"{result['message']}\n\n"

            bonuses = player._artifact_bonuses
            if bonuses.get('crit'):
                msg += f"Крит: +{bonuses['crit']}%\n"
            if bonuses.get('find_chance'):
                msg += f"Находка: +{bonuses['find_chance']}%\n"
            if bonuses.get('radiation'):
                msg += f"Радиация: {bonuses['radiation']}\n"
            if bonuses.get('energy'):
                msg += f"Энергия: +{bonuses['energy']}\n"
            if bonuses.get('defense'):
                msg += f"Защита: +{bonuses['defense']}%\n"
            if bonuses.get('dodge'):
                msg += f"Уклонение: +{bonuses['dodge']}%"
            if bonuses.get('max_health_bonus'):
                msg += f"\nЗдоровье: +{bonuses['max_health_bonus']} HP"
        else:
            msg = f"{result['message']}"

        vk.messages.send(user_id=user_id, message=msg, random_id=0)
    
    return True


# === Разделы инвентаря ===

def show_weapons(player, vk, user_id: int):
    """Показать оружие"""
    from main import create_inventory_keyboard
    import database

    player.inventory_section = 'weapons'
    database.update_user_stats(user_id, inventory_section='weapons')

    items = player.inventory.weapons
    if items:
        msg = _screen_header("Инвентарь: оружие", player) + "\n"
        for idx, item in enumerate(items, 1):
            equipped_mark = " [ЭКИП]" if item['name'] == player.equipped_weapon else ""
            msg += (
                f"{idx}. 🔫 {item['name']}{equipped_mark}\n"
                f"   Урон {item.get('attack', 0)} | Вес {_fmt_weight(item)} | x{item.get('quantity', 1)}\n"
            )
        msg += _screen_footer("надеть/снять")
    else:
        msg = _screen_header("Инвентарь: оружие", player) + "\nПусто."

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def show_armor(player, vk, user_id: int):
    """Показать броню"""
    from main import create_inventory_keyboard
    import database

    player.inventory_section = 'armor'
    database.update_user_stats(user_id, inventory_section='armor')

    items = player.inventory.armor
    if items:
        msg = _screen_header("Инвентарь: броня", player) + "\n"
        for idx, item in enumerate(items, 1):
            equipped_mark = ""
            item_name = item['name']
            # Проверяем, экипирована ли броня в любом слоте
            if item_name in [
                player.equipped_armor_head,
                player.equipped_armor_body,
                player.equipped_armor_legs,
                player.equipped_armor_hands,
                player.equipped_armor_feet
            ]:
                equipped_mark = " [ЭКИП]"
            msg += (
                f"{idx}. 🛡️ {item_name}{equipped_mark}\n"
                f"   Защита {item.get('defense', 0)} | Вес {_fmt_weight(item)} | x{item.get('quantity', 1)}\n"
            )
        msg += _screen_footer("надеть/снять")
    else:
        msg = _screen_header("Инвентарь: броня", player) + "\nПусто."

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def show_backpacks(player, vk, user_id: int):
    """Показать рюкзаки"""
    from main import create_inventory_keyboard
    import database

    player.inventory_section = 'backpacks'
    database.update_user_stats(user_id, inventory_section='backpacks')

    if player.inventory.backpacks:
        msg = _screen_header("Инвентарь: рюкзаки", player) + "\n"
        for idx, b in enumerate(player.inventory.backpacks, 1):
            equipped_mark = " [ЭКИП]" if b['name'] == player.equipped_backpack else ""
            msg += (
                f"{idx}. 🎒 {b['name']}{equipped_mark}\n"
                f"   Бонус веса +{b.get('backpack_bonus', 0)}кг | Вес {_fmt_weight(b)} | x{b.get('quantity', 1)}\n"
            )
        msg += f"\nНадето: {player.equipped_backpack or 'нет'}"
        msg += _screen_footer("надеть/снять")
    else:
        msg = _screen_header("Инвентарь: рюкзаки", player) + "\nПусто."

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def show_artifacts(player, vk, user_id: int):
    """Показать артефакты"""
    from main import create_inventory_keyboard
    import database

    player.inventory_section = 'artifacts'
    database.update_user_stats(user_id, inventory_section='artifacts')

    equipped = player.equipped_artifacts
    artifacts = player.inventory.artifacts

    msg = _screen_header("Инвентарь: артефакты", player) + "\n"

    if equipped:
        msg += f"{ui.section('Надето')}\n"
        for idx, art_name in enumerate(equipped, 1):
            art_info = database.get_item_by_name(art_name)
            if art_info:
                bonuses = []
                if art_info.get('crit_bonus'):
                    bonuses.append(f"крит:+{art_info['crit_bonus']}%")
                if art_info.get('find_bonus'):
                    bonuses.append(f"находка:+{art_info['find_bonus']}%")
                if art_info.get('radiation'):
                    bonuses.append(f"рад:{art_info['radiation']}")
                if art_info.get('energy_bonus'):
                    bonuses.append(f"энергия:+{art_info['energy_bonus']}")
                if art_info.get('defense_bonus'):
                    bonuses.append(f"защита:+{art_info['defense_bonus']}%")
                if art_info.get('dodge_bonus'):
                    bonuses.append(f"уклон:+{art_info['dodge_bonus']}%")

                bonus_str = ", ".join(bonuses) if bonuses else "без бонусов"
                msg += f"{idx}. 🔮 {art_name} [ЭКИП]\n   {bonus_str}\n"

    if artifacts:
        msg += f"\n{ui.section('В рюкзаке')}\n"
        for idx, art in enumerate(artifacts, len(equipped) + 1):
            bonuses = []
            if art.get('crit_bonus'):
                bonuses.append(f"крит:+{art['crit_bonus']}%")
            if art.get('find_bonus'):
                bonuses.append(f"находка:+{art['find_bonus']}%")
            if art.get('radiation'):
                bonuses.append(f"рад:{art['radiation']}")
            if art.get('energy_bonus'):
                bonuses.append(f"энергия:+{art['energy_bonus']}")
            if art.get('defense_bonus'):
                bonuses.append(f"защита:+{art['defense_bonus']}%")
            if art.get('dodge_bonus'):
                bonuses.append(f"уклон:+{art['dodge_bonus']}%")

            bonus_str = ", ".join(bonuses) if bonuses else "без бонусов"
            msg += (
                f"{idx}. 🔸 {art['name']}\n"
                f"   {bonus_str} | Вес {_fmt_weight(art, default=0.5)} | x{art.get('quantity', 1)}\n"
            )
        msg += _screen_footer("надеть/снять")
    elif not equipped:
        msg = _screen_header("Инвентарь: артефакты", player) + "\nПусто."

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def show_other(player, vk, user_id: int):
    """Показать другие предметы"""
    from main import create_inventory_keyboard
    import database

    player.inventory_section = 'other'
    database.update_user_stats(user_id, inventory_section='other')

    items = player.inventory.other
    if items:
        msg = _screen_header("Инвентарь: другое", player) + "\n"
        for idx, item in enumerate(items, 1):
            equipped_mark = " [ЭКИП]" if item['name'] == player.equipped_device else ""
            msg += (
                f"{idx}. 📦 {item['name']}{equipped_mark}\n"
                f"   Вес {_fmt_weight(item, default=0.5)} | x{item.get('quantity', 1)}\n"
            )
        msg += _screen_footer("использовать/экипировать")
    else:
        msg = _screen_header("Инвентарь: другое", player) + "\nПусто."

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def show_resources_shop(player, vk, user_id: int):
    """Показать ресурсы в магазине (гильзы)"""
    import database as db

    # Получаем ресурсы из магазина
    resources = db.get_items_by_category('resources')

    if not resources:
        vk.messages.send(
            user_id=user_id,
            message="Ресурсы временно недоступны.",
            random_id=0
        )
        return

    # Также добавляем мешочки для гильз
    shells_bags = db.get_items_by_category('shells_bag')

    # Формируем сообщение
    msg = "📦РЕСУРСЫ\n\n"
    msg += "Гильзы — для добычи артефактов из аномалий.\n\n"

    for idx, item in enumerate(resources, 1):
        price = item.get('price', 0)
        name = item['name']
        desc = item.get('description', '')[:50]
        weight = item.get('weight', 0.1)
        msg += f"{idx}. {name} — {price} руб.\n   {desc} Вес: {weight}кг\n\n"

    if shells_bags:
        msg += "🎒Мешочки для гильз:\n\n"
        start_idx = len(resources) + 1
        for idx, item in enumerate(shells_bags, start_idx):
            price = item.get('price', 0)
            name = item['name']
            capacity = item.get('backpack_bonus', 0)  # Вместимость
            weight = item.get('weight', 0.1)
            msg += f"{idx}. {name} — {price} руб.\n   Вместимость: {capacity} гильз. Вес: {weight}кг\n\n"

    msg += f"Твои деньги: {player.money} руб.\n"
    msg += f"Гильзы: {db.get_user_shells(user_id)} шт.\n\n"
    msg += "Напиши 'купить <номер>' или 'купить <название>'"

    vk.messages.send(user_id=user_id, message=msg, random_id=0)


def show_all(player, vk, user_id: int):
    """Показать весь инвентарь"""
    from main import create_inventory_keyboard

    player.inventory.reload()

    msg = (
        _screen_header("Инвентарь: сводка", player)
        + "\n"
        + f"{ui.section('Категории')}\n"
        + f"🔫 Оружие: {len(player.inventory.weapons)}\n"
        + f"🛡️ Броня: {len(player.inventory.armor)}\n"
        + f"🎒 Рюкзаки: {len(player.inventory.backpacks)}\n"
        + f"🔮 Артефакты: {len(player.inventory.artifacts)} (экип: {len(player.equipped_artifacts)}/{player.artifact_slots})\n"
        + f"📦 Другое: {len(player.inventory.other)}\n"
        + "\n"
        + ui.section("Подсказка")
        + "\nОткрой нужную категорию кнопками ниже — так читать проще."
    )

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def show_equipped_artifacts(player, vk, user_id: int):
    """Показать надетые артефакты"""
    from main import create_inventory_keyboard

    equipped = player.equipped_artifacts

    if not equipped:
        msg = (
            "У тебя нет надетых артефактов...\n\n"
            "Зайди в раздел 'Артефакты' чтобы надеть артефакты из инвентаря."
        )
        vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)
        return

    msg = "Надетые артефакты:\n\n"

    for idx, art_name in enumerate(equipped, 1):
        art_info = database.get_item_by_name(art_name)
        if art_info:
            bonuses = []
            if art_info.get('crit_bonus'):
                bonuses.append(f"крит:+{art_info['crit_bonus']}%")
            if art_info.get('find_bonus'):
                bonuses.append(f"находка:+{art_info['find_bonus']}%")
            if art_info.get('radiation'):
                bonuses.append(f"рад:{art_info['radiation']}")
            if art_info.get('energy_bonus'):
                bonuses.append(f"энергия:+{art_info['energy_bonus']}")
            if art_info.get('defense_bonus'):
                bonuses.append(f"защита:+{art_info['defense_bonus']}%")
            if art_info.get('dodge_bonus'):
                bonuses.append(f"уклон:+{art_info['dodge_bonus']}%")

            bonus_str = " ".join(bonuses) if bonuses else ""
            msg += f"{idx}. {art_name} {bonus_str}\n"

    msg += "\nНажми цифру чтобы снять артефакт"

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def show_artifact_slots(player, vk, user_id: int):
    """Показать слоты для артефактов"""
    from main import create_inventory_keyboard

    equipped = player.equipped_artifacts
    max_slots = player.artifact_slots

    msg = f"Слоты для артефактов:\n\n"
    msg += f"Надето: {len(equipped)}/{max_slots}\n\n"

    if len(equipped) >= max_slots:
        msg += "МАКСИМУМ СЛОТОВ!\n\n"
        msg += "Купи дополнительные слоты у Учёного на КПП."
    else:
        next_slot_cost = 500 + (max_slots - 3) * 250
        msg += f"Следующий слот: {next_slot_cost} руб.\n"
        msg += f"Твои деньги: {player.money} руб.\n\n"

        if player.money >= next_slot_cost:
            msg += "Напиши 'купить слот' чтобы приобрести."
        else:
            msg += "НЕ ХВАТАЕТ ДЕНЕГ."

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def show_artifact_help(player, vk, user_id: int):
    """Показать справку по артефактам"""
    from main import create_inventory_keyboard

    msg = (
        "ИНСТРУКЦИЯ ПО АРТЕФАКТАМ\n\n"
        "Артефакты — это аномальные образования, которые дают бонусы.\n\n"
        "Как надеть:\n"
        "1. Зайди в 'Артефакты'\n"
        "2. Нажми цифру рядом с артефактом\n\n"
        "Как снять:\n"
        "1. Зайди в 'Артефакты'\n"
        "2. Надетые артефакты в начале списка [Н]\n"
        "3. Нажми цифру чтобы снять\n\n"
        "Бонусы артефактов:\n"
        "- Крит: шанс критического удара\n"
        "- Находка: шанс найти предметы\n"
        "- Энергия: бонус к энергии\n"
        "- Защита: снижение урона\n"
        "- Уклонение: шанс уклониться\n"
        "- Радиация: ВНИМАНИЕ! Отрицательное значение лечит, положительное — наносит урон!\n\n"
        "Слоты:\n"
        "Базово 3 слота. Купи дополнительные у Учёного."
    )

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def handle_equip_backpack(player, vk, user_id: int):
    """Показать доступные рюкзаки"""
    from main import create_inventory_keyboard

    player.inventory.reload()
    backpacks = player.inventory.backpacks

    if not backpacks:
        vk.messages.send(
            user_id=user_id,
            message="У тебя нет рюкзаков в инвентаре.",
            keyboard=create_inventory_keyboard().get_keyboard(),
            random_id=0
        )
        return

    msg = "Доступные рюкзаки:\n\n"
    for idx, b in enumerate(backpacks, 1):
        msg += f"{idx}. {b['name']} +{b.get('backpack_bonus', 0)}кг ВЕС:{b.get('weight', 1.0)}кг\n"

    msg += f"\nНадето: {player.equipped_backpack or 'нет'}\n"
    msg += "\nНажми цифру чтобы надеть."

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def handle_unequip_backpack(player, vk, user_id: int):
    """Снять рюкзак"""
    success, msg = player.equip_backpack(None)
    vk.messages.send(user_id=user_id, message=msg, random_id=0)


def handle_show_use_items(player, vk, user_id: int):
    """Показать предметы для использования"""
    from main import create_inventory_keyboard

    player.inventory.reload()
    items = player.inventory.other

    if not items:
        vk.messages.send(
            user_id=user_id,
            message="У тебя нет расходуемых предметов.",
            keyboard=create_inventory_keyboard().get_keyboard(),
            random_id=0
        )
        return

    msg = "Доступно для использования:\n\n"
    for idx, item in enumerate(items, 1):
        msg += f"{idx}. {item['name']} x{item['quantity']}\n"

    msg += "\nНажми цифру чтобы использовать."

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def handle_buy_item(player, item_name: str, vk, user_id: int):
    """Купить предмет"""
    from handlers.quests import track_quest_shop_buy
    shop_data = get_shop_cache_data(user_id)
    merchant_id = shop_data.get("merchant")
    if not merchant_id:
        vk.messages.send(
            user_id=user_id,
            message="❌ Сначала открой витрину магазина (раздел с товарами), затем покупай.",
            random_id=0
        )
        return

    offered_items = []
    for key in ("weapons", "armor", "scientist", "artifacts"):
        offered_items.extend(shop_data.get(key, []))

    if merchant_id and offered_items:
        if not any(str(i.get("name", "")).lower() == item_name.lower() for i in offered_items):
            vk.messages.send(
                user_id=user_id,
                message="❌ Этого товара нет в текущей витрине. Открой раздел магазина заново.",
                random_id=0
            )
            return

    success, msg = player.buy_item(item_name, merchant_id=merchant_id)
    if success:
        track_quest_shop_buy(user_id)
    vk.messages.send(user_id=user_id, message=msg, random_id=0)


def handle_sell_item(player, item_name: str, vk, user_id: int):
    """Продать предмет"""
    from handlers.quests import track_quest_shop_sell
    shop_data = get_shop_cache_data(user_id)
    merchant_id = shop_data.get("merchant")
    if not merchant_id:
        if player.current_location_id == 'кпп':
            merchant_id = database.NPC_MERCHANT_SOLDIER
        elif player.current_location_id == 'черный рынок':
            merchant_id = database.NPC_MERCHANT_TRADER
    success, msg = player.sell_item(item_name, merchant_id=merchant_id)
    if success:
        track_quest_shop_sell(user_id)
    vk.messages.send(user_id=user_id, message=msg, random_id=0)


def handle_buy_artifact_slot(player, vk, user_id: int):
    """Купить слот для артефакта"""
    from main import create_inventory_keyboard
    import config

    max_slots = player.artifact_slots
    cost = config.ARTIFACT_SLOT_COSTS.get(max_slots + 1)

    if max_slots >= config.MAX_ARTIFACT_SLOTS:
        vk.messages.send(
            user_id=user_id,
            message=f"Нельзя купить больше слотов. Максимум: {config.MAX_ARTIFACT_SLOTS}.",
            random_id=0
        )
        return

    if not cost:
        vk.messages.send(
            user_id=user_id,
            message="Нельзя купить больше слотов.",
            random_id=0
        )
        return

    if player.level < config.MIN_LEVEL_FOR_ARTIFACT_SLOT:
        vk.messages.send(
            user_id=user_id,
            message=f"Нужен {config.MIN_LEVEL_FOR_ARTIFACT_SLOT} уровень для покупки слотов.",
            random_id=0
        )
        return

    if player.money < cost:
        vk.messages.send(
            user_id=user_id,
            message=f"Не хватает денег! Нужно: {cost} руб., у тебя: {player.money} руб.",
            random_id=0
        )
        return

    player.money -= cost
    player.artifact_slots += 1

    database.update_user_stats(
        user_id,
        money=player.money,
        artifact_slots=player.artifact_slots
    )

    vk.messages.send(
        user_id=user_id,
        message=f"Куплен слот для артефакта!\nТеперь у тебя {player.artifact_slots} слотов.\nПотрачено: {cost} руб.",
        random_id=0
    )


def handle_use_item(player, item_name: str, vk, user_id: int):
    """Использовать предмет"""
    from main import create_location_keyboard

    # Проверяем, не детектор ли это
    item_lower = item_name.lower()
    if 'детектор' in item_lower:
        # Ищем детектор в инвентаре
        player.inventory.reload()
        for item in player.inventory.other:
            if 'детектор' in item['name'].lower():
                success, msg = player.equip_device(item['name'])
                vk.messages.send(
                    user_id=user_id,
                    message=msg,
                    keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                    random_id=0
                )
                return

        vk.messages.send(
            user_id=user_id,
            message="📡 У тебя нет детектора в инвентаре.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    success, msg = player.use_item(item_name)
    vk.messages.send(
        user_id=user_id,
        message=msg,
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def handle_drop_item(player, item_name: str, vk, user_id: int):
    """Выбросить предмет"""
    from main import create_inventory_keyboard

    player.inventory.reload()

    # Проверяем, есть ли предмет в инвентаре
    all_items = (
        player.inventory.weapons +
        player.inventory.armor +
        player.inventory.artifacts +
        player.inventory.backpacks +
        player.inventory.other
    )

    item = next((i for i in all_items if i['name'].lower() == item_name.lower()), None)

    if not item:
        vk.messages.send(
            user_id=user_id,
            message=f"❌ У тебя нет предмета '{item_name}'.",
            keyboard=create_inventory_keyboard().get_keyboard(),
            random_id=0
        )
        return

    # Проверяем, не экипирован ли предмет
    if item['name'] == player.equipped_weapon:
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Сначала сними оружие: {item['name']}",
            keyboard=create_inventory_keyboard().get_keyboard(),
            random_id=0
        )
        return

    if item['name'] == player.equipped_backpack:
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Сначала сними рюкзак: {item['name']}",
            keyboard=create_inventory_keyboard().get_keyboard(),
            random_id=0
        )
        return

    # Проверяем, не экипирована ли броня
    equipped_armor = [
        player.equipped_armor_head,
        player.equipped_armor_body,
        player.equipped_armor_legs,
        player.equipped_armor_hands,
        player.equipped_armor_feet
    ]
    if item['name'] in equipped_armor:
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Сначала сними броню: {item['name']}",
            keyboard=create_inventory_keyboard().get_keyboard(),
            random_id=0
        )
        return

    # Проверяем, не экипирован ли артефакт
    if item['name'] in player.equipped_artifacts:
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Сначала сними артефакт: {item['name']}",
            keyboard=create_inventory_keyboard().get_keyboard(),
            random_id=0
        )
        return

    # Выбрасываем предмет
    result = database.drop_item_from_inventory(user_id, item['name'], 1)

    player.inventory.reload()

    vk.messages.send(
        user_id=user_id,
        message=result['message'],
        keyboard=create_inventory_keyboard().get_keyboard(),
        random_id=0
    )


def handle_drop_item_by_index(player, index: int, vk, user_id: int):
    """Выбросить предмет по номеру в текущем разделе"""
    from main import create_inventory_keyboard
    import logging
    logger = logging.getLogger(__name__)

    try:
        player.inventory.reload()

        section = player.inventory_section or 'other'

        # Получаем предметы из текущего раздела
        if section == 'weapons':
            items = player.inventory.weapons
        elif section == 'armor':
            items = player.inventory.armor
        elif section == 'backpacks':
            items = player.inventory.backpacks
        elif section == 'artifacts':
            items = player.inventory.artifacts
        elif section == 'other':
            items = player.inventory.other
        else:
            items = player.inventory.other

        logger.info(f"[DROP] section={section}, index={index}, items_count={len(items)}")

        if index < 1 or index > len(items):
            vk.messages.send(
                user_id=user_id,
                message=f"❌ Нет предмета с номером {index}.",
                keyboard=create_inventory_keyboard().get_keyboard(),
                random_id=0
            )
            return

        item = items[index - 1]
        item_name = item['name']

        logger.info(f"[DROP] item_name={item_name}")

        # Проверяем, не экипирован ли предмет
        if item_name == player.equipped_weapon:
            vk.messages.send(
                user_id=user_id,
                message=f"❌ Сначала сними оружие: {item_name}",
                keyboard=create_inventory_keyboard().get_keyboard(),
                random_id=0
            )
            return

        if item_name == player.equipped_backpack:
            vk.messages.send(
                user_id=user_id,
                message=f"❌ Сначала сними рюкзак: {item_name}",
                keyboard=create_inventory_keyboard().get_keyboard(),
                random_id=0
            )
            return

        equipped_armor = [
            player.equipped_armor_head,
            player.equipped_armor_body,
            player.equipped_armor_legs,
            player.equipped_armor_hands,
            player.equipped_armor_feet
        ]
        if item_name in equipped_armor:
            vk.messages.send(
                user_id=user_id,
                message=f"❌ Сначала сними броню: {item_name}",
                keyboard=create_inventory_keyboard().get_keyboard(),
                random_id=0
            )
            return

        if item_name in player.equipped_artifacts:
            vk.messages.send(
                user_id=user_id,
                message=f"❌ Сначала сними артефакт: {item_name}",
                keyboard=create_inventory_keyboard().get_keyboard(),
                random_id=0
            )
            return

        # Выбрасываем предмет
        result = database.drop_item_from_inventory(user_id, item_name, 1)

        logger.info(f"[DROP] result={result}")

        # Сохраняем вес для оповещения
        item_weight = item.get('weight', 0.5)

        player.inventory.reload()

        # Обновляем отображение раздела
        if section == 'weapons':
            show_weapons(player, vk, user_id)
        elif section == 'armor':
            show_armor(player, vk, user_id)
        elif section == 'backpacks':
            show_backpacks(player, vk, user_id)
        elif section == 'artifacts':
            show_artifacts(player, vk, user_id)
        else:
            show_other(player, vk, user_id)

        # Оповещение о выбрасывании
        drop_message = (
            f"🗑️Предмет выброшен!\n\n"
            f"Ты выбросил: {item_name}\n"
            f"⚖️ Освобождено: {item_weight}кг\n\n"
            f"Вещь навсегда исчезла в Зоне..."
        )
        vk.messages.send(user_id=user_id, message=drop_message, random_id=0)

    except Exception as e:
        logger.error(f"[DROP] Ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Ошибка при выбрасывании: {e}",
            random_id=0
        )


# === Магазин у военного на КПП ===

# Кэш списков товаров для покупки по номеру
_shop_cache = {}  # {user_id: {'weapons': [...], 'armor': [...]}}
_shop_cache_lock = threading.RLock()


def get_shop_cache_data(user_id: int) -> dict:
    """Потокобезопасно получить кэш магазина пользователя."""
    with _shop_cache_lock:
        return dict(_shop_cache.get(user_id, {}))


def set_shop_cache_data(user_id: int, data: dict):
    """Потокобезопасно установить кэш магазина пользователя."""
    with _shop_cache_lock:
        _shop_cache[user_id] = dict(data)


def _get_shop_items_by_number(user_id: int, category: str, number: int) -> str | None:
    """Получить название предмета по номеру в магазине"""
    with _shop_cache_lock:
        if user_id not in _shop_cache:
            return None
        items = _shop_cache[user_id].get(category, [])

    if 1 <= number <= len(items):
        return items[number - 1]['name']
    return None


def clear_shop_cache(user_id: int = None):
    """Очистить кэш магазина"""
    with _shop_cache_lock:
        if user_id:
            _shop_cache.pop(user_id, None)
        else:
            _shop_cache.clear()


def show_soldier_weapons(player, vk, user_id: int):
    """Показать оружие в магазине военного"""
    from main import create_kpp_shop_keyboard
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Очищаем старый кэш и сохраняем новый
        clear_shop_cache(user_id)

        # Проверяем, есть ли данные в БД, если нет - инициализируем
        try:
            # Используем существующую функцию для получения предметов
            all_items = database.get_all_items()
            logger.info(f"[SOLDIER_SHOP] Всего предметов: {len(all_items)}")

            if len(all_items) == 0:
                logger.info("[SOLDIER_SHOP] База данных пуста, выполняем инициализацию...")
                database.init_db()
                import time
                time.sleep(1)
                all_items = database.get_all_items()
        except Exception as e:
            logger.info(f"[SOLDIER_SHOP] Ошибка проверки БД: {e}")
            try:
                database.init_db()
                import time
                time.sleep(1)
            except:
                pass

        shop = database.get_npc_shop_assortment(
            database.NPC_MERCHANT_SOLDIER,
            category='weapons',
            limit=10,
        )
        weapons = shop.get("items", [])
        logger.info(f"[SOLDIER_SHOP] Загружено оружия в витрине: {len(weapons)}")
        set_shop_cache_data(user_id, {
            'merchant': database.NPC_MERCHANT_SOLDIER,
            'weapons': weapons,
            'period_key': shop.get("period_key"),
        })

        if not weapons:
            vk.messages.send(
                user_id=user_id,
                message="🎖️Военный:\n\n«Оружия нет в наличии. Загляни позже.»",
                keyboard=create_kpp_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return

        msg = f"{ui.title('Военный склад: оружие')}\n"
        msg += f"💰 Баланс: {player.money} руб.\n\n"
        event_text = shop.get("event_text")
        if event_text:
            msg += f"📣 {event_text}\n\n"

        for idx, weapon in enumerate(weapons, 1):
            name = weapon['name']
            price = weapon.get('price', 0)
            base_price = weapon.get('base_price', price)
            attack = weapon.get('attack', 0)
            weight = weapon.get('weight', 1.0)
            desc = weapon.get('description', '')[:40]
            stock_left = weapon.get('stock_left', 0)
            is_featured = weapon.get('is_featured', False)
            featured = " ⭐ ТОВАР ДНЯ" if is_featured else ""

            msg += f"{idx}. {name}{featured}\n"
            msg += f"   🔫 Урон: {attack} | Вес: {weight}кг\n"
            msg += f"   📝 {desc}\n"
            if is_featured and base_price != price:
                msg += f"   💵 Цена: {price} руб. (было {base_price})\n"
            else:
                msg += f"   💵 Цена: {price} руб.\n"
            msg += f"   📦 Остаток: {stock_left} шт.\n\n"

        msg += "Напиши 'купить <номер>' или 'купить <название>'"

        vk.messages.send(
            user_id=user_id,
            message=msg,
            keyboard=create_kpp_shop_keyboard().get_keyboard(),
            random_id=0
        )
    except Exception as e:
        logger.error(f"[SOLDIER_SHOP] Ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Ошибка при загрузке оружия: {e}",
            random_id=0
        )


def show_soldier_armor(player, vk, user_id: int):
    """Показать броню в магазине военного"""
    from main import create_kpp_shop_keyboard
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Очищаем старый кэш и сохраняем новый
        clear_shop_cache(user_id)

        # Проверяем, есть ли данные в БД
        try:
            all_items = database.get_all_items()
            logger.info(f"[SOLDIER_SHOP] Всего предметов: {len(all_items)}")

            if len(all_items) == 0:
                logger.info("[SOLDIER_SHOP] База данных пуста, выполняем инициализацию...")
                database.init_db()
                import time
                time.sleep(1)
        except Exception as e:
            logger.info(f"[SOLDIER_SHOP] Ошибка проверки БД: {e}")
            try:
                database.init_db()
                import time
                time.sleep(1)
            except:
                pass

        shop = database.get_npc_shop_assortment(
            database.NPC_MERCHANT_SOLDIER,
            category='armor',
            limit=10,
        )
        armor_list = shop.get("items", [])
        logger.info(f"[SOLDIER_SHOP] Загружено брони в витрине: {len(armor_list)}")
        set_shop_cache_data(user_id, {
            'merchant': database.NPC_MERCHANT_SOLDIER,
            'armor': armor_list,
            'period_key': shop.get("period_key"),
        })

        if not armor_list:
            vk.messages.send(
                user_id=user_id,
                message="🎖️Военный:\n\n«Брони нет в наличии. Загляни позже.»",
                keyboard=create_kpp_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return

        msg = f"{ui.title('Военный склад: броня')}\n"
        msg += f"💰 Баланс: {player.money} руб.\n\n"
        event_text = shop.get("event_text")
        if event_text:
            msg += f"📣 {event_text}\n\n"

        for idx, armor in enumerate(armor_list, 1):
            name = armor['name']
            price = armor.get('price', 0)
            base_price = armor.get('base_price', price)
            defense = armor.get('defense', 0)
            weight = armor.get('weight', 1.0)
            desc = armor.get('description', '')[:40]
            stock_left = armor.get('stock_left', 0)
            is_featured = armor.get('is_featured', False)
            featured = " ⭐ ТОВАР ДНЯ" if is_featured else ""

            msg += f"{idx}. {name}{featured}\n"
            msg += f"   🛡️ Защита: {defense} | Вес: {weight}кг\n"
            msg += f"   📝 {desc}\n"
            if is_featured and base_price != price:
                msg += f"   💵 Цена: {price} руб. (было {base_price})\n"
            else:
                msg += f"   💵 Цена: {price} руб.\n"
            msg += f"   📦 Остаток: {stock_left} шт.\n\n"

        msg += "Напиши 'купить <номер>' или 'купить <название>'"

        vk.messages.send(
            user_id=user_id,
            message=msg,
            keyboard=create_kpp_shop_keyboard().get_keyboard(),
            random_id=0
        )
    except Exception as e:
        logger.error(f"[SOLDIER_SHOP] Ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Ошибка при загрузке брони: {e}",
            random_id=0
        )


def show_scientist_shop(player, vk, user_id: int, category: str = 'all'):
    """Показать медикаменты и еду в магазине учёного"""
    from main import create_scientist_shop_keyboard
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Очищаем старый кэш и сохраняем новый
        clear_shop_cache(user_id)

        # Проверяем, есть ли данные в БД
        try:
            all_items = database.get_all_items()
            logger.info(f"[SCIENTIST_SHOP] Всего предметов: {len(all_items)}")

            # Покажем все категории
            cats = {}
            for item in all_items:
                cat = item.get('category', 'unknown')
                cats[cat] = cats.get(cat, 0) + 1
            logger.info(f"[SCIENTIST_SHOP] Категории: {cats}")

            if len(all_items) == 0:
                database.init_db()
                import time
                time.sleep(1)
        except Exception as e:
            logger.info(f"[SCIENTIST_SHOP] Ошибка: {e}")

        # Меню выбора категорий
        if category == 'all':
            vk.messages.send(
                user_id=user_id,
                message="🔬Учёный:\n\n«Выбирай, сталкер:\n\n💊 Лекарства — аптечки, бинты, стимуляторы\n⚡ Энергетики — еда и напитки\n\nЦены честные, научные!»",
                keyboard=create_scientist_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return

        # Получаем категорию meds или food
        if category == 'meds':
            shop = database.get_npc_shop_assortment(
                database.NPC_MERCHANT_SCIENTIST,
                category='meds',
                limit=10,
            )
            items = shop.get("items", [])
            title = "ЛЕКАРСТВА"
        else:
            shop = database.get_npc_shop_assortment(
                database.NPC_MERCHANT_SCIENTIST,
                category='food',
                limit=10,
            )
            items = shop.get("items", [])
            title = "ЭНЕРГЕТИКИ"

        logger.info(f"[SCIENTIST_SHOP] Категория consumables: {len(items)} предметов")
        set_shop_cache_data(user_id, {
            'merchant': database.NPC_MERCHANT_SCIENTIST,
            'scientist': items,
            'category': category,
            'period_key': shop.get("period_key"),
        })

        if not items:
            vk.messages.send(
                user_id=user_id,
                message="🔬Учёный:\n\n«Лекарств пока нет. Загляни позже.»",
                keyboard=create_scientist_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return

        msg = f"{ui.title(f'Лаборатория: {title.lower()}')}\n"
        msg += f"💰 Баланс: {player.money} руб.\n\n"
        event_text = shop.get("event_text")
        if event_text:
            msg += f"📣 {event_text}\n\n"

        for idx, item in enumerate(items, 1):
            name = item['name']
            price = item.get('price', 0)
            base_price = item.get('base_price', price)
            weight = item.get('weight', 0.1)
            desc = item.get('description', '')[:35]
            stock_left = item.get('stock_left', 0)
            is_featured = item.get('is_featured', False)
            featured = " ⭐ ТОВАР ДНЯ" if is_featured else ""
            msg += f"{idx}. {name}{featured}\n"
            msg += f"   📝 {desc}\n"
            if is_featured and base_price != price:
                msg += f"   💵 Цена: {price} руб. (было {base_price}) | Вес: {weight}кг\n"
            else:
                msg += f"   💵 Цена: {price} руб. | Вес: {weight}кг\n"
            msg += f"   📦 Остаток: {stock_left} шт.\n\n"

        msg += "Напиши 'купить <номер>' или 'купить <название>'\n"
        msg += "\nНажми 'Назад' для выбора категории"

        vk.messages.send(
            user_id=user_id,
            message=msg,
            keyboard=create_scientist_shop_keyboard().get_keyboard(),
            random_id=0
        )
    except Exception as e:
        logger.error(f"[SCIENTIST_SHOP] Ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Ошибка при загрузке магазина: {e}",
            random_id=0
        )


# === Магазин артефактов на Черном рынке ===

def show_artifact_shop(player, vk, user_id: int, rarity: str = None):
    """Показать артефакты в магазине"""
    from handlers.keyboards import create_artifact_shop_keyboard
    import logging
    logger = logging.getLogger(__name__)

    try:
        clear_shop_cache(user_id)

        # Категории артефактов - используем редкость вместо категории
        rarity_map = {
            'common': ('common', 'ОБЫЧНЫЕ'),
            'rare': ('rare', 'РЕДКИЕ'),
            'unique': ('unique', 'УНИКАЛЬНЫЕ'),
            'legendary': ('legendary', 'ЛЕГЕНДАРНЫЕ'),
        }

        # Показать меню выбора
        if not rarity:
            vk.messages.send(
                user_id=user_id,
                message="🔮АРТЕФАКТЫ\n\nВыбери редкость:\n\n"
                        "🔹 Обычные — Медуза, Камень, Пульсатор и др.\n"
                        "🔹 Редкие — Метеорит, Огненный камень и др.\n"
                        "🔹 Уникальные — Вечный, Феникс и др.\n"
                        "🔹 Легендарные — Душа, Мечта и др.",
                keyboard=create_artifact_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return

        # Получаем категорию и название
        rarity_key, title = rarity_map.get(rarity, ('common', 'ОБЫЧНЫЕ'))
        shop = database.get_npc_shop_assortment(
            database.NPC_MERCHANT_TRADER,
            category='artifacts',
            limit=10,
            rarity=rarity_key,
        )
        items = shop.get("items", [])

        if not items:
            vk.messages.send(
                user_id=user_id,
                message=f"🔮Артефакты {title}\n\nНет в наличии.",
                keyboard=create_artifact_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return

        set_shop_cache_data(user_id, {
            'merchant': database.NPC_MERCHANT_TRADER,
            'artifacts': items,
            'rarity': rarity,
            'period_key': shop.get("period_key"),
        })

        msg = f"{ui.title(f'Артефакты: {title.lower()}')}\n"
        msg += f"💰 Баланс: {player.money} руб.\n\n"
        event_text = shop.get("event_text")
        if event_text:
            msg += f"📣 {event_text}\n\n"

        for idx, item in enumerate(items, 1):
            name = item['name']
            price = item.get('price', 0)
            base_price = item.get('base_price', price)
            weight = item.get('weight', 0.1)
            desc = item.get('description', '')[:35]
            stock_left = item.get('stock_left', 0)
            is_featured = item.get('is_featured', False)
            featured = " ⭐ ТОВАР ДНЯ" if is_featured else ""

            # Показываем бонусы
            bonuses = []
            if item.get('crit_bonus'):
                bonuses.append(f"крит:+{item['crit_bonus']}%")
            if item.get('find_bonus'):
                bonuses.append(f"находка:+{item['find_bonus']}%")
            if item.get('radiation'):
                bonuses.append(f"рад:{item['radiation']}")
            if item.get('energy_bonus'):
                bonuses.append(f"энергия:+{item['energy_bonus']}")
            if item.get('defense_bonus'):
                bonuses.append(f"защита:+{item['defense_bonus']}%")
            if item.get('dodge_bonus'):
                bonuses.append(f"уклон:+{item['dodge_bonus']}%")

            bonus_str = f" ({', '.join(bonuses)})" if bonuses else ""

            msg += f"{idx}. {name}{bonus_str}{featured}\n"
            msg += f"   📝 {desc}\n"
            if is_featured and base_price != price:
                msg += f"   💵 Цена: {price} руб. (было {base_price}) | Вес: {weight}кг\n"
            else:
                msg += f"   💵 Цена: {price} руб. | Вес: {weight}кг\n"
            msg += f"   📦 Остаток: {stock_left} шт.\n\n"

        msg += "Напиши 'купить <номер>' или 'купить <название>'\n"
        msg += "\nНажми 'Назад' для выбора редкости"

        vk.messages.send(
            user_id=user_id,
            message=msg,
            keyboard=create_artifact_shop_keyboard().get_keyboard(),
            random_id=0
        )
    except Exception as e:
        logger.error(f"[ARTIFACT_SHOP] Ошибка: {e}")
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Ошибка при загрузке артефактов: {e}",
            random_id=0
        )


def show_sell_artifacts(player, vk, user_id: int):
    """Показать артефакты игрока для продажи"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        player.inventory.reload()
        artifacts = player.inventory.artifacts

        if not artifacts:
            vk.messages.send(
                user_id=user_id,
                message="💰ПРОДАЖА АРТЕФАКТОВ\n\nУ тебя нет артефактов для продажи.\n\n"
                        "Артефакты можно найти в аномалиях на дорогах.",
                random_id=0
            )
            return

        # Сохраняем в кэш для продажи по номеру
        set_shop_cache_data(user_id, {
            'merchant': database.NPC_MERCHANT_TRADER,
            'sell_artifacts': artifacts,
        })

        msg = "💰ПРОДАЖА АРТЕФАКТОВ\n\n"
        msg += f"💰 Твои деньги: {player.money} руб.\n\n"
        event_text = database.get_shop_event_text(database.NPC_MERCHANT_TRADER)
        if event_text:
            msg += f"📣 {event_text}\n\n"

        for idx, art in enumerate(artifacts, 1):
            name = art['name']
            price_preview = database.get_npc_sell_price_preview(
                name,
                merchant_id=database.NPC_MERCHANT_TRADER,
                sell_bonus_pct=player.sell_bonus,
            )
            base_price = price_preview["sell_price"] if price_preview else 50
            weight = art.get('weight', 0.1)

            bonuses = []
            item_info = database.get_item_by_name(name)
            if item_info and item_info.get('crit_bonus'):
                bonuses.append(f"крит:+{item_info['crit_bonus']}%")
            if item_info and item_info.get('find_bonus'):
                bonuses.append(f"находка:+{item_info['find_bonus']}%")
            if item_info and item_info.get('radiation'):
                bonuses.append(f"рад:{item_info['radiation']}")

            bonus_str = f" ({', '.join(bonuses)})" if bonuses else ""
            msg += f"{idx}. {name}{bonus_str}\n"
            msg += f"   💵 Продам за: ~{base_price} руб.\n"
            msg += f"   ⚖️ Вес: {weight}кг\n\n"

        msg += "Напиши 'продать <номер>' или 'продать <название>'\n"
        msg += "\nНажми 'Назад' для возврата в магазин"

        vk.messages.send(
            user_id=user_id,
            message=msg,
            random_id=0
        )
    except Exception as e:
        logger.error(f"[SELL_ARTIFACTS] Ошибка: {e}")
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Ошибка: {e}",
            random_id=0
        )


def handle_sell_artifact_by_number(player, vk, user_id: int, item_num: str) -> bool:
    """Продать артефакт по номеру"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        shop_data = get_shop_cache_data(user_id)
        artifacts = shop_data.get('sell_artifacts', [])

        if not artifacts:
            return False

        try:
            idx = int(item_num) - 1
            if 0 <= idx < len(artifacts):
                artifact = artifacts[idx]
                artifact_name = artifact['name']
                return handle_sell_artifact(player, artifact_name, vk, user_id)
            else:
                vk.messages.send(user_id=user_id, message="Нет артефакта с таким номером.", random_id=0)
                return True
        except ValueError:
            return False

    except Exception as e:
        logger.error(f"[SELL_ARTIFACT_BY_NUMBER] Ошибка: {e}")
        return False


def handle_sell_artifact(player, artifact_name: str, vk, user_id: int) -> bool:
    """Продать артефакт по названию"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        player.inventory.reload()
        artifacts = player.inventory.artifacts

        # Ищем артефакт
        artifact = None
        for art in artifacts:
            if art['name'].lower() == artifact_name.lower():
                artifact = art
                break
            if artifact_name.lower() in art['name'].lower():
                artifact = art
                break

        if not artifact:
            vk.messages.send(
                user_id=user_id,
                message=f"❌ У тебя нет артефакта '{artifact_name}'.",
                random_id=0
            )
            return True

        artifact_name = artifact['name']
        item_info = database.get_item_by_name(artifact_name)

        if not item_info:
            vk.messages.send(
                user_id=user_id,
                message=f"❌ Информация об артефакте не найдена.",
                random_id=0
            )
            return True

        # Продаем
        success, msg = player.sell_item(artifact_name, merchant_id=database.NPC_MERCHANT_TRADER)

        if success:
            from handlers.quests import track_quest_shop_sell
            track_quest_shop_sell(user_id)
            vk.messages.send(
                user_id=user_id,
                message=f"💰Артефакт продан!\n\n🔮 {artifact_name}\n{msg}",
                random_id=0
            )

            # Показываем снова список артефактов
            show_sell_artifacts(player, vk, user_id)
        else:
            vk.messages.send(user_id=user_id, message=msg, random_id=0)

        return True

    except Exception as e:
        logger.error(f"[SELL_ARTIFACT] Ошибка: {e}")
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Ошибка при продаже: {e}",
            random_id=0
        )
        return True


# === Покупка артефактов ===

def handle_buy_artifact(player, item_name: str, vk, user_id: int) -> bool:
    """Купить артефакт"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Ищем артефакт в кэше магазина
        shop_data = get_shop_cache_data(user_id)
        artifacts = shop_data.get('artifacts', [])

        artifact = None

        # Если передано число - ищем по номеру
        if item_name.isdigit():
            idx = int(item_name) - 1
            if 0 <= idx < len(artifacts):
                artifact = artifacts[idx]
        else:
            # Ищем по названию
            for art in artifacts:
                if art['name'].lower() == item_name.lower():
                    artifact = art
                    break
            # Частичное совпадение
            if not artifact:
                for art in artifacts:
                    if item_name.lower() in art['name'].lower():
                        artifact = art
                        break

        if not artifact:
            vk.messages.send(
                user_id=user_id,
                message=f"❌ Артефакт '{item_name}' не найден в магазине.",
                random_id=0
            )
            return True

        price = artifact.get('price', 0)
        weight = artifact.get('weight', 0.1)
        artifact_name = artifact['name']

        # Проверяем деньги
        if player.money < price:
            vk.messages.send(
                user_id=user_id,
                message=f"💸Недостаточно денег!\n\n"
                        f"Цена: {price} руб.\n"
                        f"У тебя: {player.money} руб.\n"
                        f"Не хватает: {price - player.money} руб.",
                random_id=0
            )
            return True

        # Проверяем вес
        current_weight = player.inventory.total_weight
        max_weight = player.max_weight
        if current_weight + weight > max_weight:
            vk.messages.send(
                user_id=user_id,
                message=f"🎒Не хватает места!\n\n"
                        f"Текущий вес: {current_weight:.1f} / {max_weight} кг\n"
                        f"Вес артефакта: {weight} кг",
                random_id=0
            )
            return True

        # Покупаем
        success, msg = player.buy_item(artifact_name, merchant_id=database.NPC_MERCHANT_TRADER)

        if success:
            from handlers.quests import track_quest_shop_buy
            track_quest_shop_buy(user_id)
            player.inventory.reload()

            vk.messages.send(
                user_id=user_id,
                message=f"✅Артефакт куплен!\n\n"
                        f"🔮 {artifact_name}\n"
                        f"💵 Потрачено: {price} руб.\n"
                        f"⚖️ Вес: {weight} кг\n\n"
                        f"💰 Остаток: {player.money} руб.",
                random_id=0
            )

            # Показываем артефакты снова
            rarity = shop_data.get('rarity')
            show_artifact_shop(player, vk, user_id, rarity)
        else:
            vk.messages.send(user_id=user_id, message=msg, random_id=0)

        return True

    except Exception as e:
        logger.error(f"[BUY_ARTIFACT] Ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Ошибка при покупке: {e}",
            random_id=0
        )
        return True
