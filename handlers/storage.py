"""
Шкаф-хранилище в убежище.
"""
from __future__ import annotations

from infra import database
from infra.state_manager import get_ui_current_screen, set_ui_screen, try_edit_or_send_ui
from handlers.keyboards import create_location_keyboard, create_storage_keyboard


STORAGE_PAGE_SIZE = 10


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
        return None, "Укажи предмет: например в шкаф 2 бинт."

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


def _storage_page_bounds(total_items: int, page: int = 0) -> tuple[int, int, int, int]:
    total_pages = max(1, (max(0, int(total_items)) + STORAGE_PAGE_SIZE - 1) // STORAGE_PAGE_SIZE)
    safe_page = max(0, min(total_pages - 1, int(page or 0)))
    start = safe_page * STORAGE_PAGE_SIZE
    end = start + STORAGE_PAGE_SIZE
    return safe_page, total_pages, start, end


def _current_storage_page(user_id: int) -> int:
    current = get_ui_current_screen(user_id)
    if current.get("name") != "storage":
        return 0
    return int(current.get("page", 0) or 0)


def _storage_item_name_by_index(storage: list[dict], target: str) -> tuple[str | None, str | None]:
    if not str(target or "").isdigit():
        return None, None

    index = int(target)
    if index <= 0:
        return None, "Номер должен быть от 1."
    if index > len(storage):
        return None, f"В шкафу нет предмета с номером {index}."
    return str(storage[index - 1].get("name") or "").strip(), None


def format_storage_page(storage: list[dict], load: dict, page: int = 0) -> tuple[str, int, int]:
    safe_page, total_pages, start, end = _storage_page_bounds(len(storage), page)
    current = int(load["current"])
    capacity = int(load["capacity"])

    lines = [
        "🗄️ ШКАФ УБЕЖИЩА",
        f"Страница: {safe_page + 1}/{total_pages}",
        f"Заполнение: {current}/{capacity} слотов",
        "",
    ]
    if not storage:
        lines.append("Шкаф пуст.")
    else:
        lines.append("Содержимое:")
        for idx, item in enumerate(storage[start:end], start + 1):
            lines.append(f"{idx}. {item['name']} x{int(item.get('quantity', 1) or 1)}")

    lines += [
        "",
        "Команды:",
        "• <номер> — забрать 1 шт. из шкафа",
        "• в шкаф <предмет>",
        "• в шкаф <кол-во> <предмет>",
        "• из шкафа <номер|предмет>",
        "• из шкафа <кол-во> <предмет>",
        "• из шкафа <кол-во> <номер>",
    ]
    return "\n".join(lines), safe_page, total_pages


def show_storage(player, vk, user_id: int, page: int = 0):
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
    message, safe_page, total_pages = format_storage_page(storage, load, page)
    current_ui = get_ui_current_screen(user_id)
    push_current = current_ui.get("name") != "storage"
    set_ui_screen(user_id, {"name": "storage", "page": safe_page}, push_current=push_current)
    try_edit_or_send_ui(
        vk,
        user_id,
        "storage",
        message,
        keyboard=create_storage_keyboard(safe_page, total_pages).get_keyboard(),
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
    show_storage(player, vk, user_id, page=_current_storage_page(user_id))


def take_from_storage(player, vk, user_id: int, payload: str):
    if player.current_location_id != "убежище":
        vk.messages.send(
            user_id=user_id,
            message="Шкаф доступен только в убежище.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    raw_payload = str(payload or "").strip()
    if raw_payload.isdigit():
        parsed = (1, raw_payload)
    else:
        parsed = _parse_transfer_payload(raw_payload)
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
    indexed_name, index_error = _storage_item_name_by_index(storage, item_name)
    if index_error:
        vk.messages.send(
            user_id=user_id,
            message=f"❌ {index_error}",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return
    if indexed_name:
        item_name = indexed_name

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
    show_storage(player, vk, user_id, page=_current_storage_page(user_id))


def handle_storage_callback(player, vk, user_id: int, payload: dict) -> bool:
    if payload.get("command") != "storage_page":
        return False
    show_storage(player, vk, user_id, int(payload.get("page", 0) or 0))
    return True
