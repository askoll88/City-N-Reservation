"""
Шкаф-хранилище в убежище.
"""
from __future__ import annotations

from infra import database
from handlers.keyboards import create_location_keyboard


def _all_player_items(player) -> list[dict]:
    player.inventory.reload()
    return (
        player.inventory.weapons
        + player.inventory.armor
        + player.inventory.backpacks
        + player.inventory.artifacts
        + player.inventory.shells_bags
        + player.inventory.other
    )


def _parse_transfer_payload(payload: str) -> tuple[int, str] | tuple[None, str]:
    raw = (payload or "").strip()
    if not raw:
        return None, "Укажи предмет: например `в шкаф 2 бинт`."

    parts = raw.split(maxsplit=1)
    if parts[0].isdigit():
        qty = int(parts[0])
        if qty <= 0:
            return None, "Количество должно быть больше нуля."
        if len(parts) < 2 or not parts[1].strip():
            return None, "После количества укажи название предмета."
        return qty, parts[1].strip()
    return 1, raw


def _equipped_block_reason(player, item_name: str) -> str | None:
    if item_name == player.equipped_weapon:
        return "Сначала сними оружие."
    if item_name == player.equipped_backpack:
        return "Сначала сними рюкзак."
    if item_name == player.equipped_device:
        return "Сначала сними устройство."

    equipped_armor = {
        player.equipped_armor,
        player.equipped_armor_head,
        player.equipped_armor_body,
        player.equipped_armor_legs,
        player.equipped_armor_hands,
        player.equipped_armor_feet,
    }
    if item_name in equipped_armor:
        return "Сначала сними броню."
    if item_name in set(player.equipped_artifacts):
        return "Сначала сними артефакт."

    user_data = database.get_user_by_vk(player.user_id) or {}
    if item_name == user_data.get("equipped_shells_bag"):
        return "Сначала сними мешочек для гильз."
    return None


def show_storage(player, vk, user_id: int):
    if player.current_location_id != "убежище":
        vk.messages.send(
            user_id=user_id,
            message="Шкаф доступен только в убежище.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    storage = database.get_user_storage(user_id)
    load = database.get_user_storage_load(user_id)
    current = int(load["current"])
    capacity = int(load["capacity"])

    lines = [
        "🗄️ ШКАФ УБЕЖИЩА",
        f"Заполнение: {current}/{capacity} слотов",
        "",
    ]
    if not storage:
        lines.append("Шкаф пуст.")
    else:
        lines.append("Содержимое:")
        for idx, item in enumerate(storage, 1):
            lines.append(f"{idx}. {item['name']} x{int(item.get('quantity', 1) or 1)}")

    lines += [
        "",
        "Команды:",
        "• в шкаф <предмет>",
        "• в шкаф <кол-во> <предмет>",
        "• из шкафа <предмет>",
        "• из шкафа <кол-во> <предмет>",
    ]
    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
        random_id=0,
    )


def put_to_storage(player, vk, user_id: int, payload: str):
    if player.current_location_id != "убежище":
        vk.messages.send(
            user_id=user_id,
            message="Шкаф доступен только в убежище.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    parsed = _parse_transfer_payload(payload)
    if parsed[0] is None:
        vk.messages.send(
            user_id=user_id,
            message=f"❌ {parsed[1]}",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return
    qty, item_name = parsed

    items = _all_player_items(player)
    item = next((i for i in items if i["name"].lower() == item_name.lower()), None)
    if not item:
        vk.messages.send(
            user_id=user_id,
            message=f"❌ У тебя нет предмета '{item_name}'.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    item_name = item["name"]
    block_reason = _equipped_block_reason(player, item_name)
    if block_reason:
        vk.messages.send(
            user_id=user_id,
            message=f"❌ {block_reason}",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    tx = database.move_item_to_storage_transaction(user_id, item_name, qty)
    if not tx.get("success"):
        vk.messages.send(
            user_id=user_id,
            message=f"❌ {tx.get('message', 'Не удалось переложить предмет.')}",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    player.inventory.reload()
    show_storage(player, vk, user_id)


def take_from_storage(player, vk, user_id: int, payload: str):
    if player.current_location_id != "убежище":
        vk.messages.send(
            user_id=user_id,
            message="Шкаф доступен только в убежище.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    parsed = _parse_transfer_payload(payload)
    if parsed[0] is None:
        vk.messages.send(
            user_id=user_id,
            message=f"❌ {parsed[1]}",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return
    qty, item_name = parsed

    storage = database.get_user_storage(user_id)
    st_item = next((i for i in storage if i["name"].lower() == item_name.lower()), None)
    if not st_item:
        vk.messages.send(
            user_id=user_id,
            message=f"❌ В шкафу нет предмета '{item_name}'.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    item_name = st_item["name"]
    item_weight = float(st_item.get("weight", 0.0) or 0.0)
    player.inventory.reload()
    new_weight = float(player.inventory.total_weight) + item_weight * qty
    if new_weight > float(player.max_weight):
        vk.messages.send(
            user_id=user_id,
            message=(
                f"❌ Не хватает места в рюкзаке.\n"
                f"Вес после переноса: {new_weight:.1f}/{float(player.max_weight):.1f}кг."
            ),
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    tx = database.move_item_from_storage_transaction(user_id, item_name, qty)
    if not tx.get("success"):
        vk.messages.send(
            user_id=user_id,
            message=f"❌ {tx.get('message', 'Не удалось забрать предмет.')}",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    player.inventory.reload()
    show_storage(player, vk, user_id)
