"""
Обработчики инвентаря
"""
import database
from constants import InventorySection


def handle_inventory_digit(player, text: str, vk, user_id: int) -> bool:
    """Обработка цифр 1-9 в инвентаре. Возвращает True если обработано."""
    from main import create_inventory_keyboard
    
    if not text.isdigit() or not (1 <= int(text) <= 9):
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
    armor_defense = armor.get('defense', 0)
    
    player.armor_defense = armor_defense
    database.update_user_stats(user_id, equipped_armor=armor_name, armor_defense=armor_defense)
    
    vk.messages.send(
        user_id=user_id,
        message=f"Надета броня: {armor_name}! Защита: +{armor_defense}",
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
        else:
            msg = f"{result['message']}"

        vk.messages.send(user_id=user_id, message=msg, random_id=0)
    
    return True


# === Разделы инвентаря ===

def show_weapons(player, vk, user_id: int):
    """Показать оружие"""
    from main import create_inventory_keyboard
    
    database.update_user_stats(user_id, inventory_section='weapons')
    player.inventory_section = 'weapons'
    
    items = player.inventory.weapons
    if items:
        msg = "Оружие:\n" + "\n".join(
            f"{idx}. {item['name']} x{item['quantity']} УРН:{item.get('attack', 0)} ВЕС:{item.get('weight', 1.0)}кг"
            for idx, item in enumerate(items, 1)
        )
        msg += "\n\nНажми цифру чтобы надеть"
    else:
        msg = "Оружие: Пусто"

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def show_armor(player, vk, user_id: int):
    """Показать броню"""
    from main import create_inventory_keyboard
    
    database.update_user_stats(user_id, inventory_section='armor')
    player.inventory_section = 'armor'
    
    items = player.inventory.armor
    if items:
        msg = "Броня:\n" + "\n".join(
            f"{idx}. {item['name']} x{item['quantity']} ЗАЩ:{item.get('defense', 0)} ВЕС:{item.get('weight', 1.0)}кг"
            for idx, item in enumerate(items, 1)
        )
        msg += "\n\nНажми цифру чтобы надеть"
    else:
        msg = "Броня: Пусто"

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def show_backpacks(player, vk, user_id: int):
    """Показать рюкзаки"""
    from main import create_inventory_keyboard
    
    database.update_user_stats(user_id, inventory_section='backpacks')
    player.inventory_section = 'backpacks'
    
    if player.inventory.backpacks:
        backpack_list = "\n".join(
            f"{idx}. {b['name']} +{b.get('backpack_bonus', 0)}кг ВЕС:{b.get('weight', 1.0)}кг"
            for idx, b in enumerate(player.inventory.backpacks, 1)
        )
        current = f"\n\nНадето: {player.equipped_backpack or 'нет'}\nНажми цифру чтобы надеть"
        msg = f"Рюкзаки:\n\n{backpack_list}{current}"
    else:
        msg = "Рюкзаки: Пусто"

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def show_artifacts(player, vk, user_id: int):
    """Показать артефакты"""
    from main import create_inventory_keyboard

    database.update_user_stats(user_id, inventory_section='artifacts')
    player.inventory_section = 'artifacts'

    equipped = player.equipped_artifacts
    artifacts = player.inventory.artifacts

    msg = "Артефакты:\n\n"

    if equipped:
        msg += "Надето:\n"
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
                msg += f"{idx}. [Н] {art_name} {bonus_str}\n"

    if artifacts:
        msg += "\nВ инвентаре:\n"
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

            bonus_str = " ".join(bonuses) if bonuses else ""
            weight = art.get('weight', 0.5)
            msg += f"{idx}. {art['name']} {bonus_str} ВЕС:{weight}кг\n"
        msg += "\nНажми цифру чтобы надеть/снять"
    elif not equipped:
        msg = "Артефакты: Пусто"

    vk.messages.send(user_id=user_id, message=msg, keyboard=create_inventory_keyboard().get_keyboard(), random_id=0)


def show_other(player, vk, user_id: int):
    """Показать другие предметы"""
    from main import create_inventory_keyboard

    database.update_user_stats(user_id, inventory_section='other')
    player.inventory_section = 'other'

    items = player.inventory.other
    if items:
        msg = "Другое:\n" + "\n".join(
            f"{idx}. {item['name']} x{item['quantity']} ВЕС:{item.get('weight', 0.5)}кг"
            for idx, item in enumerate(items, 1)
        )
        msg += "\n\nНажми цифру чтобы использовать"
    else:
        msg = "Другое: Пусто"

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
    msg = "📦 <b>РЕСУРСЫ</b>\n\n"
    msg += "Гильзы — для добычи артефактов из аномалий.\n\n"

    for idx, item in enumerate(resources, 1):
        price = item.get('price', 0)
        name = item['name']
        desc = item.get('description', '')[:50]
        weight = item.get('weight', 0.1)
        msg += f"{idx}. {name} — {price} руб.\n   {desc} Вес: {weight}кг\n\n"

    if shells_bags:
        msg += "🎒 <b>Мешочки для гильз:</b>\n\n"
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

    msg = "Весь инвентарь:\n\n"

    if player.inventory.weapons:
        msg += "Оружие:\n" + "\n".join(
            f"- {item['name']} x{item['quantity']} УРН:{item.get('attack', 0)} ВЕС:{item.get('weight', 1.0)}кг"
            for item in player.inventory.weapons
        ) + "\n\n"
    else:
        msg += "Оружие: пусто\n\n"

    if player.inventory.armor:
        msg += "Броня:\n" + "\n".join(
            f"- {item['name']} x{item['quantity']} ЗАЩ:{item.get('defense', 0)} ВЕС:{item.get('weight', 1.0)}кг"
            for item in player.inventory.armor
        ) + "\n\n"
    else:
        msg += "Броня: пусто\n\n"

    if player.inventory.backpacks:
        msg += "Рюкзаки:\n" + "\n".join(
            f"- {item['name']} +{item.get('backpack_bonus', 0)}кг ВЕС:{item.get('weight', 1.0)}кг"
            for item in player.inventory.backpacks
        ) + "\n\n"
    else:
        msg += "Рюкзаки: пусто\n\n"

    if player.inventory.artifacts:
        msg += "Артефакты:\n" + "\n".join(
            f"- {item['name']} x{item['quantity']} ВЕС:{item.get('weight', 0.5)}кг"
            for item in player.inventory.artifacts
        ) + "\n\n"
    else:
        msg += "Артефакты: пусто\n\n"

    if player.inventory.other:
        msg += "Другое:\n" + "\n".join(
            f"- {item['name']} x{item['quantity']} ВЕС:{item.get('weight', 0.5)}кг"
            for item in player.inventory.other
        )
    else:
        msg += "Другое: пусто"

    msg += f"\n\nОбщий вес: {player.inventory.total_weight}/{player.max_weight}кг"

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
    success, msg = player.buy_item(item_name)
    vk.messages.send(user_id=user_id, message=msg, random_id=0)


def handle_sell_item(player, item_name: str, vk, user_id: int):
    """Продать предмет"""
    success, msg = player.sell_item(item_name)
    vk.messages.send(user_id=user_id, message=msg, random_id=0)


def handle_buy_artifact_slot(player, vk, user_id: int):
    """Купить слот для артефакта"""
    from main import create_inventory_keyboard

    max_slots = player.artifact_slots
    next_slot_cost = 500 + (max_slots - 3) * 250

    if max_slots >= 10:
        vk.messages.send(
            user_id=user_id,
            message="Нельзя купить больше слотов. Максимум: 10.",
            random_id=0
        )
        return

    if player.money < next_slot_cost:
        vk.messages.send(
            user_id=user_id,
            message=f"Не хватает денег! Нужно: {next_slot_cost} руб., у тебя: {player.money} руб.",
            random_id=0
        )
        return

    player.money -= next_slot_cost
    player.artifact_slots += 1

    database.update_user_stats(
        user_id,
        money=player.money,
        artifact_slots=player.artifact_slots
    )

    vk.messages.send(
        user_id=user_id,
        message=f"Куплен слот для артефакта!\nТеперь у тебя {player.artifact_slots} слотов.\nПотрачено: {next_slot_cost} руб.",
        random_id=0
    )


def handle_use_item(player, item_name: str, vk, user_id: int):
    """Использовать предмет"""
    from main import create_location_keyboard

    success, msg = player.use_item(item_name)
    vk.messages.send(
        user_id=user_id,
        message=msg,
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


# === Магазин у военного на КПП ===

# Кэш списков товаров для покупки по номеру
_shop_cache = {}  # {user_id: {'weapons': [...], 'armor': [...]}}


def _get_shop_items_by_number(user_id: int, category: str, number: int) -> str | None:
    """Получить название предмета по номеру в магазине"""
    global _shop_cache

    if user_id not in _shop_cache:
        _shop_cache[user_id] = {}

    if category not in _shop_cache[user_id]:
        items = database.get_items_by_category(category)
        _shop_cache[user_id][category] = items

    items = _shop_cache[user_id].get(category, [])
    if 1 <= number <= len(items):
        return items[number - 1]['name']
    return None


def clear_shop_cache(user_id: int = None):
    """Очистить кэш магазина"""
    global _shop_cache
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

        # Используем кэш предметов из database
        all_weapons = database.get_items_by_category('weapons')
        # Ограничиваем до 10 предметов (VK лимит)
        weapons = all_weapons[:10]
        logger.info(f"[SOLDIER_SHOP] Загружено оружия: {len(weapons)} из {len(all_weapons)}")
        _shop_cache[user_id] = {'weapons': weapons}

        if not weapons:
            vk.messages.send(
                user_id=user_id,
                message="🎖️ <b>Военный:</b>\n\n«Оружия нет в наличии. Загляни позже.»",
                keyboard=create_kpp_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return

        msg = "🎖️ <b>ВОЕННЫЙ СКЛАД — ОРУЖИЕ</b>\n\n"
        msg += f"💰 Твои деньги: {player.money} руб.\n\n"

        for idx, weapon in enumerate(weapons, 1):
            name = weapon['name']
            price = weapon.get('price', 0)
            attack = weapon.get('attack', 0)
            weight = weapon.get('weight', 1.0)
            desc = weapon.get('description', '')[:40]

            msg += f"{idx}. {name}\n"
            msg += f"   🔫 Урон: {attack} | Вес: {weight}кг\n"
            msg += f"   📝 {desc}\n"
            msg += f"   💵 Цена: {price} руб.\n\n"

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

        # Используем кэш предметов из database
        all_armor = database.get_items_by_category('armor')
        # Ограничиваем до 10 предметов (VK лимит)
        armor_list = all_armor[:10]
        logger.info(f"[SOLDIER_SHOP] Загружено брони: {len(armor_list)} из {len(all_armor)}")
        _shop_cache[user_id] = {'armor': armor_list}

        if not armor_list:
            vk.messages.send(
                user_id=user_id,
                message="🎖️ <b>Военный:</b>\n\n«Брони нет в наличии. Загляни позже.»",
                keyboard=create_kpp_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return

        msg = "🎖️ <b>ВОЕННЫЙ СКЛАД — БРОНЯ</b>\n\n"
        msg += f"💰 Твои деньги: {player.money} руб.\n\n"

        for idx, armor in enumerate(armor_list, 1):
            name = armor['name']
            price = armor.get('price', 0)
            defense = armor.get('defense', 0)
            weight = armor.get('weight', 1.0)
            desc = armor.get('description', '')[:40]

            msg += f"{idx}. {name}\n"
            msg += f"   🛡️ Защита: {defense} | Вес: {weight}кг\n"
            msg += f"   📝 {desc}\n"
            msg += f"   💵 Цена: {price} руб.\n\n"

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
                message="🔬 <b>Учёный:</b>\n\n«Выбирай, сталкер:\n\n💊 Лекарства — аптечки, бинты, стимуляторы\n⚡ Энергетики — еда и напитки\n\nЦены честные, научные!»",
                keyboard=create_scientist_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return

        # Получаем категорию meds или food
        if category == 'meds':
            items = database.get_items_by_category('meds')[:10]
            title = "ЛЕКАРСТВА"
        else:
            items = database.get_items_by_category('food')[:10]
            title = "ЭНЕРГЕТИКИ"

        logger.info(f"[SCIENTIST_SHOP] Категория consumables: {len(items)} предметов")
        _shop_cache[user_id] = {'scientist': items, 'category': category}

        if not items:
            vk.messages.send(
                user_id=user_id,
                message="🔬 <b>Учёный:</b>\n\n«Лекарств пока нет. Загляни позже.»",
                keyboard=create_scientist_shop_keyboard().get_keyboard(),
                random_id=0
            )
            return

        msg = f"🔬 <b>ЛАБОРАТОРИЯ — {title}</b>\n\n"
        msg += f"💰 Твои деньги: {player.money} руб.\n\n"

        for idx, item in enumerate(items, 1):
            name = item['name']
            price = item.get('price', 0)
            weight = item.get('weight', 0.1)
            desc = item.get('description', '')[:35]
            msg += f"{idx}. {name}\n"
            msg += f"   📝 {desc}\n"
            msg += f"   💵 Цена: {price} руб. | Вес: {weight}кг\n\n"

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


