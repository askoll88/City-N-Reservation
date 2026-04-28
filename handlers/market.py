"""
P2P рынок игроков (черный рынок)
"""
from __future__ import annotations

import json
import re
import time

from infra import config
from infra import database
from handlers.keyboards import (
    create_player_market_keyboard,
    create_purchase_confirm_keyboard,
    create_market_pagination_keyboard,
    create_market_listing_keyboard,
    create_my_listings_keyboard,
    create_market_search_keyboard,
)
from infra.state_manager import (
    set_pending_purchase,
    clear_pending_purchase,
    has_pending_purchase,
    get_pending_purchase,
    set_market_browse_state,
    get_market_browse_state,
    clear_market_browse_state,
    set_market_my_listings_page,
    get_market_my_listings_page,
    _market_browse_state,
)

# Категория-маппинг для кнопок
CATEGORY_MAP = {
    "все лоты": None,
    "оружие": "weapons",
    "броня": "armor",
    "артефакты": "artifacts",
    "медицина": "meds",
    "еда": "food",
}

SORT_MAP = {
    "🆕 новые": "newest",
    "📅 старые": "oldest",
    "💰 дешевле": "cheap",
    "💎 дороже": "expensive",
}

PER_PAGE = 8  # Лотов на страницу


def _notify_user(vk, user_id: int, message: str):
    """Безопасная отправка уведомления пользователю."""
    try:
        vk.messages.send(user_id=user_id, message=message, random_id=0)
    except Exception:
        # Уведомления не должны ломать основной сценарий рынка.
        pass


def _resolve_player_item_name(player, item_input: str) -> tuple[str, dict | None]:
    """Найти каноничное имя предмета из инвентаря игрока."""
    name_raw = (item_input or "").strip()
    if not name_raw:
        return "", None

    try:
        player.inventory.reload()
        all_items = (
            player.inventory.weapons +
            player.inventory.armor +
            player.inventory.artifacts +
            player.inventory.backpacks +
            player.inventory.other
        )
        inv_match = next((i for i in all_items if (i.get("name", "").lower() == name_raw.lower())), None)
        if inv_match:
            canon = inv_match.get("name", name_raw)
            return canon, (database.get_item_by_name(canon) or inv_match)
    except Exception:
        pass

    item_info = database.get_item_by_name(name_raw)
    if item_info:
        return item_info.get("name", name_raw), item_info
    return name_raw, None


def _get_price_bounds_for_item(item_info: dict | None) -> tuple[int, int] | None:
    """Получить допустимый диапазон цены для лота."""
    if not item_info:
        return None

    # Предпочитаем общую бизнес-логику из database.py
    calc_fn = getattr(database, "_get_market_price_bounds", None)
    if callable(calc_fn):
        try:
            min_p, max_p = calc_fn(item_info)
            return int(min_p), int(max_p)
        except Exception:
            pass

    base_price = int(item_info.get("price") or 0)
    if base_price <= 0:
        return None
    rarity = str(item_info.get("rarity") or "common").lower()
    if rarity == "rare":
        mn, mx = config.MARKET_PRICE_MIN_MULT_RARE, config.MARKET_PRICE_MAX_MULT_RARE
    elif rarity == "unique":
        mn, mx = config.MARKET_PRICE_MIN_MULT_UNIQUE, config.MARKET_PRICE_MAX_MULT_UNIQUE
    elif rarity == "legendary":
        mn, mx = config.MARKET_PRICE_MIN_MULT_LEGENDARY, config.MARKET_PRICE_MAX_MULT_LEGENDARY
    else:
        mn, mx = config.MARKET_PRICE_MIN_MULT_COMMON, config.MARKET_PRICE_MAX_MULT_COMMON
    min_price = max(1, int(base_price * mn))
    max_price = max(min_price, int(base_price * mx))
    return min_price, max_price


def _sanitize_keyboard_payload(keyboard_payload: str, max_cols: int = 2) -> str:
    """
    Принудительно ограничить количество кнопок в строке.
    Предохранитель от VK API 911 (row contains too much columns).
    """
    try:
        data = json.loads(keyboard_payload)
        rows = data.get("buttons", [])
        safe_rows = []
        for row in rows:
            if not isinstance(row, list):
                continue
            trimmed = row[:max_cols]
            # Пустые строки не отправляем
            if trimmed:
                safe_rows.append(trimmed)
        data["buttons"] = safe_rows
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return keyboard_payload


def _start_listing_flow(user_id: int):
    """Запустить пошаговый сценарий выставления лота."""
    def updater(s):
        s = s or {}
        s["listing_flow"] = {"step": "item"}
        return s
    _market_browse_state.update(user_id, updater)


def _clear_listing_flow(user_id: int):
    """Очистить пошаговый сценарий выставления лота."""
    def updater(s):
        s = s or {}
        s.pop("listing_flow", None)
        return s
    _market_browse_state.update(user_id, updater)


def _get_listing_flow(state: dict) -> dict | None:
    flow = state.get("listing_flow")
    return flow if isinstance(flow, dict) else None


def _handle_listing_flow(player, vk, user_id: int, text: str, state: dict) -> bool:
    """Пошаговый мастер выставления лота без ручной команды."""
    flow = _get_listing_flow(state)
    if not flow:
        return False

    text_raw = text.strip()
    text_lower = text_raw.lower()
    if text_lower in ("✖️ отмена", "отмена", "отменить", "назад"):
        _clear_listing_flow(user_id)
        vk.messages.send(
            user_id=user_id,
            message="❌ Выставление лота отменено.",
            keyboard=create_player_market_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    step = flow.get("step", "item")

    if step == "item":
        if len(text_raw) < 2:
            vk.messages.send(
                user_id=user_id,
                message="Напиши название предмета из инвентаря. Пример: АК-74",
                keyboard=create_market_search_keyboard().get_keyboard(),
                random_id=0,
            )
            return True

        item_name, item_info = _resolve_player_item_name(player, text_raw)
        flow["item_name"] = item_name
        flow["item_info"] = item_info or {}
        bounds = _get_price_bounds_for_item(item_info)
        if bounds:
            flow["min_price"], flow["max_price"] = bounds
        flow["step"] = "price"
        _market_browse_state.update(user_id, lambda s: {**(s or {}), "listing_flow": flow})

        price_hint = ""
        if flow.get("min_price") and flow.get("max_price"):
            price_hint = (
                f"\nДопустимый диапазон: "
                f"{int(flow['min_price']):,}..{int(flow['max_price']):,} руб/шт"
            )
        vk.messages.send(
            user_id=user_id,
            message=(
                f"📦 Предмет: {flow['item_name']}\n\n"
                "Шаг 2/3: укажи цену за 1 шт. (целое число)\n"
                f"Пример: 1500{price_hint}"
            ),
            keyboard=create_market_search_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    if step == "price":
        if not text_raw.isdigit() or int(text_raw) <= 0:
            vk.messages.send(
                user_id=user_id,
                message="Цена должна быть положительным числом. Пример: 1500",
                keyboard=create_market_search_keyboard().get_keyboard(),
                random_id=0,
            )
            return True

        input_price = int(text_raw)
        min_p = flow.get("min_price")
        max_p = flow.get("max_price")
        if min_p is not None and max_p is not None and not (int(min_p) <= input_price <= int(max_p)):
            vk.messages.send(
                user_id=user_id,
                message=(
                    f"Цена вне диапазона: {int(min_p):,}..{int(max_p):,} руб/шт.\n"
                    "Введи корректную цену."
                ),
                keyboard=create_market_search_keyboard().get_keyboard(),
                random_id=0,
            )
            return True

        flow["price"] = input_price
        flow["step"] = "qty"
        _market_browse_state.update(user_id, lambda s: {**(s or {}), "listing_flow": flow})
        vk.messages.send(
            user_id=user_id,
            message=(
                f"📦 {flow['item_name']} | 💵 {flow['price']:,} руб/шт\n\n"
                "Шаг 3/3: укажи количество (или напиши 'пропустить' для 1 шт.)"
            ),
            keyboard=create_market_search_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    if step == "qty":
        qty = 1
        if text_lower not in ("пропустить", "skip", "1"):
            if not text_raw.isdigit() or int(text_raw) <= 0:
                vk.messages.send(
                    user_id=user_id,
                    message="Количество должно быть положительным числом или 'пропустить'.",
                    keyboard=create_market_search_keyboard().get_keyboard(),
                    random_id=0,
                )
                return True
            qty = int(text_raw)

        item_name = flow.get("item_name", "").strip()
        price = int(flow.get("price", 0) or 0)
        _clear_listing_flow(user_id)

        if not item_name or price <= 0:
            vk.messages.send(
                user_id=user_id,
                message="⚠️ Данные выставления повреждены. Начни заново: «Выставить лот».",
                keyboard=create_player_market_keyboard().get_keyboard(),
                random_id=0,
            )
            return True

        result = database.create_market_listing(user_id, item_name, price, qty)
        if result.get("success"):
            from handlers.quests import track_quest_market_list
            track_quest_market_list(user_id, vk=vk)

        vk.messages.send(
            user_id=user_id,
            message=result.get("message", "Не удалось выставить лот."),
            keyboard=create_player_market_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    _clear_listing_flow(user_id)
    return True


def _format_listing(row: dict) -> str:
    """Компактный формат одного лота."""
    rarity_emoji = {"common": "⚪", "rare": "🔵", "unique": "🟣", "legendary": "🟡"}.get(
        row.get("rarity", "common"), "⚪")
    category_name = {
        "weapons": "🔫 Оружие",
        "rare_weapons": "🔫 Редкое оружие",
        "armor": "🛡️ Броня",
        "backpacks": "🎒 Рюкзаки",
        "artifacts": "💎 Артефакты",
        "meds": "💊 Медицина",
        "food": "🍖 Еда",
        "devices": "📟 Устройства",
    }.get(row.get("category", ""), row.get("category", ""))

    lines = [
        f"📦 #{row['id']} | {row['item_name']} x{row['quantity']}",
        f"💵 {row['price_per_item']:,} руб/шт | Итого: {row['total_price']:,} руб.",
        f"{category_name} | {rarity_emoji}",
    ]
    return "\n".join(lines)


def _show_market_listings_page(player, vk, user_id, page,
                                category=None, sort="newest", search=None):
    """Показать страницу лотов рынка с пагинацией."""
    data = database.get_market_listings(page=page, per_page=PER_PAGE,
                                         category=category, sort=sort, search=search)
    listings = data["listings"]
    total = data["total"]
    pages = data["pages"]
    cur_page = data["page"]

    # Сохраняем состояние
    set_market_browse_state(user_id, category=category, page=cur_page,
                            sort=sort, search=search, view="all")
    if user_id in _market_browse_state:
        _market_browse_state[user_id]["searching"] = False
        _market_browse_state[user_id]["pages"] = pages

    if not listings:
        msg_parts = ["📭 На рынке пока нет подходящих лотов."]
        if search:
            msg_parts.append(f"По запросу '{search}' ничего не найдено.")
        if category:
            msg_parts.append("Попробуй другую категорию или отключи фильтр.")

        vk.messages.send(
            user_id=user_id,
            message="\n\n".join(msg_parts),
            keyboard=create_player_market_keyboard().get_keyboard(),
            random_id=0,
        )
        return

    # Формируем сообщение
    header = "📈 РЫНОК СТАЛКЕРОВ"
    if category:
        cat_name = {v: k for k, v in CATEGORY_MAP.items() if v}.get(category, category)
        header += f" | {cat_name.capitalize()}"
    if search:
        header += f" | 🔍 '{search}'"

    sort_name = {"newest": "🆕 Новые", "oldest": "📅 Старые",
                 "cheap": "💰 Дешевле", "expensive": "💎 Дороже"}.get(sort, "")

    header += f"\n{sort_name} | Страница {cur_page}/{pages} | Всего: {total} лотов"

    lines = [header, ""]
    for row in listings:
        lines.append(_format_listing(row))
        lines.append("─" * 20)

    lines.append(f"\n💡 Чтобы купить: купить лот <id>")
    lines.append(f"💡 Чтобы выставить: выставить <предмет> <цена> [кол-во]")
    lines.append(f"💡 Чтобы снять: снять лот <id>")

    keyboard = create_market_pagination_keyboard(cur_page, pages, category=category,
                                                   sort=sort, search=search)
    keyboard_payload = _sanitize_keyboard_payload(keyboard.get_keyboard(), max_cols=2)

    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=keyboard_payload,
        random_id=0,
    )


def show_market_menu(player, vk, user_id):
    """Главное меню рынка."""
    if not database.is_market_enabled():
        vk.messages.send(
            user_id=user_id,
            message="⛔ P2P рынок временно находится на техническом обслуживании.",
            keyboard=create_player_market_keyboard().get_keyboard(),
            random_id=0,
        )
        return

    vk.messages.send(
        user_id=user_id,
        message=(
            "📈 РЫНОК СТАЛКЕРОВ\n\n"
            "Здесь сталкеры торгуют между собой через эскроу.\n"
            "Рынок берет комиссию за безопасность сделки.\n\n"
            f"🔒 Доступ с {config.MARKET_MIN_LEVEL} уровня\n"
            f"🧾 Комиссия выставления: {config.MARKET_LISTING_FEE_PCT}%\n"
            f"💸 Комиссия продажи: {config.MARKET_SALE_FEE_PCT}% (с продавца)\n"
            f"📦 Лимит лотов: {config.MARKET_MAX_LISTINGS_PER_USER}\n"
            f"⏱️ Срок лота: {config.MARKET_LISTING_TTL_HOURS}ч\n\n"
            "Быстрый старт:\n"
            "• Открыть лоты: «Все лоты»\n"
            "• Продать: «Выставить лот» (пошагово) или командой\n"
            "• Купить: купить лот <id>"
        ),
        keyboard=create_player_market_keyboard().get_keyboard(),
        random_id=0,
    )


def show_market_listings(player, vk, user_id, category=None, page=1, sort="newest", search=None):
    """Показать лоты рынка с пагинацией."""
    _show_market_listings_page(player, vk, user_id, page, category, sort, search)


def handle_market_callback(player, vk, user_id: int, payload: dict) -> bool:
    """Обработать callback-кнопки просмотра рынка."""
    command = payload.get("command")
    state = get_market_browse_state(user_id) or {}
    category = state.get("category")
    page = int(state.get("page", 1) or 1)
    sort = state.get("sort", "newest")
    search = state.get("search")
    pages = max(1, int(state.get("pages", 1) or 1))

    if command == "market_open":
        clear_market_browse_state(user_id)
        _show_market_listings_page(player, vk, user_id, 1, None, "newest", None)
        return True

    if command == "market_category":
        target_category = payload.get("category")
        if target_category not in {"weapons", "armor", "artifacts", "meds", "food"}:
            target_category = None
        _show_market_listings_page(player, vk, user_id, 1, target_category, sort, None)
        return True

    if command == "market_my_listings":
        my_page, my_status = get_market_my_listings_page(user_id)
        show_my_market_listings(player, vk, user_id, page=my_page, status=my_status)
        return True

    if command == "market_transactions":
        show_my_market_transactions(player, vk, user_id)
        return True

    if command == "market_page":
        target_page = int(payload.get("page", page) or page)
        target_page = max(1, min(pages, target_page))
        _show_market_listings_page(player, vk, user_id, target_page, category, sort, search)
        return True

    if command == "market_sort":
        target_sort = payload.get("sort") or "newest"
        if target_sort not in {"newest", "oldest", "cheap", "expensive"}:
            target_sort = "newest"
        _show_market_listings_page(player, vk, user_id, 1, category, target_sort, search)
        return True

    if command == "market_clear_filter":
        _show_market_listings_page(player, vk, user_id, 1, None, sort, None)
        return True

    if command == "market_home":
        clear_market_browse_state(user_id)
        show_market_menu(player, vk, user_id)
        return True

    return False


def show_my_market_listings(player, vk, user_id, page=1, status="active"):
    """Показать свои лоты с пагинацией."""
    data = database.get_market_user_listings(user_id, status=status, page=page, per_page=PER_PAGE)
    listings = data["listings"]
    total = data["total"]
    pages = data["pages"]
    cur_page = data["page"]

    set_market_my_listings_page(user_id, page=cur_page, status=status)

    if not listings:
        status_name = {"active": "активных", "sold": "проданных", "all": ""}.get(status, "")
        vk.messages.send(
            user_id=user_id,
            message=f"📭 У тебя нет {status_name} лотов." if status_name else "📭 У тебя нет лотов.",
            keyboard=create_my_listings_keyboard(cur_page, pages).get_keyboard(),
            random_id=0,
        )
        return

    status_title = {"active": "АКТИВНЫЕ ЛОТЫ", "sold": "ПРОДАННЫЕ ЛОТЫ",
                    "cancelled": "СНЯТЫЕ ЛОТЫ", "expired": "ИСТЁКШИЕ ЛОТЫ",
                    "all": "ВСЕ ЛОТЫ"}.get(status, "ЛОТЫ")

    lines = [f"🧾 МОИ {status_title}",
             f"Страница {cur_page}/{pages} | Всего: {total}", ""]

    for row in listings:
        status_emoji = {"active": "🟢", "sold": "✅", "cancelled": "❌", "expired": "⏰"}.get(row["status"], "⚪")
        lines.append(
            f"{status_emoji} #{row['id']} | {row['item_name']} x{row['quantity']} | "
            f"{row['price_per_item']:,} руб/шт | Итого {row['total_price']:,} руб."
        )

    if status == "active":
        lines.append(f"\n💡 Снять лот: снять лот <id>")

    keyboard = create_my_listings_keyboard(cur_page, pages)
    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=keyboard.get_keyboard(),
        random_id=0,
    )


def show_my_market_transactions(player, vk, user_id):
    """Показать историю сделок."""
    rows = database.get_market_user_transactions(user_id, limit=30)
    if not rows:
        vk.messages.send(
            user_id=user_id,
            message="📭 Сделок пока нет.",
            keyboard=create_player_market_keyboard().get_keyboard(),
            random_id=0,
        )
        return

    lines = ["📒 МОИ СДЕЛКИ\n"]
    for row in rows:
        side = "🟢 Покупка" if row["buyer_vk_id"] == user_id else "🔵 Продажа"
        lines.append(
            f"{side} | Лот #{row['listing_id']} | {row['item_name']} x{row['quantity']} | "
            f"{row['total_price']:,} руб. | {row['created_at']:%d.%m.%Y %H:%M}"
        )

    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=create_player_market_keyboard().get_keyboard(),
        random_id=0,
    )


def handle_market_create_listing(player, vk, user_id, text):
    """Обработка создания лота: выставить <предмет> <цена> [кол-во]"""
    m = re.match(r"^выставить\s+(.+?)\s+(\d+)(?:\s+(\d+))?$", text.strip(), flags=re.IGNORECASE)
    if not m:
        return False

    item_name = m.group(1).strip()
    price = int(m.group(2))
    qty = int(m.group(3)) if m.group(3) else 1

    result = database.create_market_listing(user_id, item_name, price, qty)
    if result.get("success"):
        from handlers.quests import track_quest_market_list
        track_quest_market_list(user_id, vk=vk)
    vk.messages.send(
        user_id=user_id,
        message=result.get("message", "Не удалось выставить лот."),
        keyboard=create_player_market_keyboard().get_keyboard(),
        random_id=0,
    )
    return True


def handle_market_buy_listing(player, vk, user_id, text):
    """Показать подтверждение покупки вместо мгновенной покупки"""
    m = re.match(r"^купить\s+лот\s+(\d+)$", text.strip(), flags=re.IGNORECASE)
    if not m:
        return False

    if has_pending_purchase(user_id):
        vk.messages.send(
            user_id=user_id,
            message="⏳ У тебя уже есть неподтверждённая покупка. Подтверди или отмени её сначала.",
            keyboard=create_purchase_confirm_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    listing_id = int(m.group(1))
    lot_info = database.get_market_listing_info(listing_id)
    if not lot_info:
        vk.messages.send(
            user_id=user_id,
            message="❌ Лот не найден или уже недоступен.",
            keyboard=create_player_market_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    if lot_info["seller_vk_id"] == user_id:
        vk.messages.send(
            user_id=user_id,
            message="❌ Нельзя купить свой лот.",
            keyboard=create_player_market_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    if player.level < config.MARKET_MIN_LEVEL:
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Рынок доступен с {config.MARKET_MIN_LEVEL} уровня. У тебя {player.level}.",
            keyboard=create_player_market_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    total_price = lot_info["price_per_item"] * lot_info["quantity"]
    from game.weapon_progression import get_weapon_required_level, is_weapon
    item_info = database.get_item_by_name(lot_info["item_name"])
    if is_weapon(item_info):
        required_level = get_weapon_required_level(item_info)
        if required_level > player.level + 3:
            vk.messages.send(
                user_id=user_id,
                message=(
                    f"❌ {lot_info['item_name']} относится к оружию {required_level} уровня.\n"
                    f"Твой уровень: {player.level}. Это оружие пока нельзя купить."
                ),
                keyboard=create_player_market_keyboard().get_keyboard(),
                random_id=0,
            )
            return True

    if player.money < total_price:
        vk.messages.send(
            user_id=user_id,
            message=f"❌ Не хватает денег. Нужно {total_price:,} руб., у тебя {player.money:,} руб.",
            keyboard=create_player_market_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    set_pending_purchase(user_id, {
        "listing_id": listing_id,
        "item_name": lot_info["item_name"],
        "quantity": lot_info["quantity"],
        "price_per_item": lot_info["price_per_item"],
        "total_price": total_price,
        "seller_vk_id": lot_info["seller_vk_id"],
        "category": lot_info.get("category", "unknown"),
        "rarity": lot_info.get("rarity", "common"),
    })

    vk.messages.send(
        user_id=user_id,
        message=(
            f"🛒 ПОДТВЕРЖДЕНИЕ ПОКУПКИ\n\n"
            f"📦 {lot_info['item_name']} x{lot_info['quantity']}\n"
            f"💵 {lot_info['price_per_item']:,} руб/шт\n"
            f"💰 Итого: {total_price:,} руб.\n"
            f"👤 Продавец: {lot_info['seller_vk_id']}\n"
            f"🏷️ {lot_info.get('category', 'unknown')} | ✨ {lot_info.get('rarity', 'common')}\n\n"
            f"У тебя: {player.money:,} руб.\n"
            f"После покупки: {player.money - total_price:,} руб.\n\n"
            f"Подтвердить покупку?"
        ),
        keyboard=create_purchase_confirm_keyboard().get_keyboard(),
        random_id=0,
    )
    return True


def handle_market_confirm_purchase(player, vk, user_id, text):
    """Обработка подтверждения или отмены покупки"""
    if not has_pending_purchase(user_id):
        return False

    text_lower = text.strip().lower()

    if text_lower in ["❌ отмена", "отмена", "отменить", "нет", "cancel"]:
        pending = get_pending_purchase(user_id)
        clear_pending_purchase(user_id)

        if pending:
            vk.messages.send(
                user_id=user_id,
                message=(
                    f"❌ Покупка отменена.\n\n"
                    f"📦 {pending['item_name']} x{pending['quantity']} — {pending['total_price']:,} руб."
                ),
                keyboard=create_player_market_keyboard().get_keyboard(),
                random_id=0,
            )
        return True

    if text_lower in ["✅ подтвердить", "подтвердить", "подтверждение", "да", "yes", "купить"]:
        pending = get_pending_purchase(user_id)
        if not pending or time.time() - pending.get("start_time", 0) > 300:
            clear_pending_purchase(user_id)
            vk.messages.send(
                user_id=user_id,
                message="⚠️ Данные о покупке устарели. Попробуй снова.",
                keyboard=create_player_market_keyboard().get_keyboard(),
                random_id=0,
            )
            return True

        listing_id = pending["listing_id"]
        total_price = pending["total_price"]

        if player.money < total_price:
            clear_pending_purchase(user_id)
            vk.messages.send(
                user_id=user_id,
                message=f"❌ Не хватает денег. Нужно {total_price:,} руб., у тебя {player.money:,} руб.",
                keyboard=create_player_market_keyboard().get_keyboard(),
                random_id=0,
            )
            return True

        result = database.buy_market_listing(user_id, listing_id)
        clear_pending_purchase(user_id)

        if result.get("success"):
            from handlers.quests import track_quest_market_buy
            track_quest_market_buy(user_id, vk=vk)
            vk.messages.send(
                user_id=user_id,
                message=f"✅ {result['message']}",
                keyboard=create_player_market_keyboard().get_keyboard(),
                random_id=0,
            )
            seller_vk_id = int(result.get("seller_vk_id", 0) or 0)
            if seller_vk_id > 0:
                _notify_user(
                    vk,
                    seller_vk_id,
                    (
                        "💸 СДЕЛКА ПО ЛОТУ\n\n"
                        f"Лот #{result.get('listing_id')} продан.\n"
                        f"Покупатель: {result.get('buyer_vk_id')}\n"
                        f"Предмет: {result.get('item_name')} x{result.get('quantity')}\n"
                        f"Сумма: {int(result.get('total_price', 0) or 0):,} руб.\n"
                        f"Комиссия: {int(result.get('sale_fee', 0) or 0):,} руб.\n"
                        f"Зачислено: {int(result.get('seller_payout', 0) or 0):,} руб."
                    ),
                )
        else:
            vk.messages.send(
                user_id=user_id,
                message=f"❌ {result.get('message', 'Не удалось купить лот.')}",
                keyboard=create_player_market_keyboard().get_keyboard(),
                random_id=0,
            )
        return True

    return False


def handle_market_cancel_listing(player, vk, user_id, text):
    """Обработка снятия лота: снять лот <id>"""
    m = re.match(r"^(снять|отменить)\s+лот\s+(\d+)$", text.strip(), flags=re.IGNORECASE)
    if not m:
        return False

    listing_id = int(m.group(2))
    result = database.cancel_market_listing(user_id, listing_id)
    vk.messages.send(
        user_id=user_id,
        message=result.get("message", "Не удалось снять лот."),
        keyboard=create_player_market_keyboard().get_keyboard(),
        random_id=0,
    )
    if result.get("success"):
        _notify_user(
            vk,
            user_id,
            (
                "📭 ЛОТ СНЯТ С РЫНКА\n\n"
                f"Лот #{result.get('listing_id')} снят.\n"
                f"Предмет: {result.get('item_name')} x{result.get('quantity')}\n"
                "Предмет возвращён в инвентарь."
            ),
        )
    return True


def handle_market_input(player, vk, user_id, text):
    """
    Универсальный обработчик ввода на рынке.
    Обрабатывает кнопки пагинации, сортировки, поиска и навигации.
    """
    text_lower = text.strip().lower()

    # Состояние просмотра
    state = get_market_browse_state(user_id) or {}
    category = state.get("category")
    page = state.get("page", 1)
    sort = state.get("sort", "newest")
    search = state.get("search")
    searching = state.get("searching", False)
    pages = max(1, int(state.get("pages", 1) or 1))

    # --- Пошаговое выставление лота ---
    if _handle_listing_flow(player, vk, user_id, text, state):
        return True

    if text_lower in ("➕ выставить лот", "выставить лот"):
        _start_listing_flow(user_id)
        vk.messages.send(
            user_id=user_id,
            message=(
                "🧾 ВЫСТАВЛЕНИЕ ЛОТА\n\n"
                "Шаг 1/3: напиши название предмета из инвентаря.\n"
                "Пример: АК-74\n\n"
                "Для отмены: «Отмена»"
            ),
            keyboard=create_market_search_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    if text_lower in ("✖️ отмена", "отмена", "отменить"):
        if searching:
            # Возврат к предыдущему состоянию ленты
            _show_market_listings_page(player, vk, user_id, page, category, sort, search)
        else:
            show_market_menu(player, vk, user_id)
        return True

    # --- Режим поиска: пользователь ввёл запрос ---
    if searching:
        if text_lower in ("🏠 главная", "главная", "🏠"):
            clear_market_browse_state(user_id)
            show_market_menu(player, vk, user_id)
            return True
        # Повторная кнопка "Поиск" в режиме ввода - просто напоминаем, что нужен текст
        if text_lower in ("🔍 поиск", "поиск", "🔍 найти", "найти"):
            vk.messages.send(
                user_id=user_id,
                message="Введи текст для поиска (например: АК-74, Медуза, Аптечка) или нажми «Отмена».",
                keyboard=create_market_search_keyboard().get_keyboard(),
                random_id=0,
            )
            return True
        query = text.strip()
        if len(query) < 2:
            vk.messages.send(
                user_id=user_id,
                message="Запрос слишком короткий. Введи минимум 2 символа.",
                keyboard=create_market_search_keyboard().get_keyboard(),
                random_id=0,
            )
            return True
        clear_market_browse_state(user_id)
        _show_market_listings_page(player, vk, user_id, 1, None, "newest", query)
        return True

    # --- Навигация по страницам ---
    if text_lower in ("◀️ назад", "назад") and page > 1:
        _show_market_listings_page(player, vk, user_id, page - 1, category, sort, search)
        return True

    if text_lower in ("▶️ вперёд", "вперёд") and page < pages:
        _show_market_listings_page(player, vk, user_id, page + 1, category, sort, search)
        return True

    # Номер страницы (кнопки "📄 2" или просто "2")
    page_match = re.match(r"^📄\s*(\d+)$", text.strip())
    if page_match:
        p = int(page_match.group(1))
        if 1 <= p <= pages:
            _show_market_listings_page(player, vk, user_id, p, category, sort, search)
            return True

    if text_lower.isdigit():
        p = int(text_lower)
        if 1 <= p <= pages:
            _show_market_listings_page(player, vk, user_id, p, category, sort, search)
            return True

    # --- Сортировка ---
    sort_mapping = {
        "🆕 новые": "newest", "новые": "newest",
        "📅 старые": "oldest", "старые": "oldest",
        "💰 дешевле": "cheap", "дешевле": "cheap",
        "💎 дороже": "expensive", "дороже": "expensive",
    }
    if text_lower in sort_mapping:
        _show_market_listings_page(player, vk, user_id, 1, category, sort_mapping[text_lower], search)
        return True

    # --- Главная ---
    if text_lower in ("🏠 главная", "главная", "🏠"):
        clear_market_browse_state(user_id)
        show_market_menu(player, vk, user_id)
        return True

    # --- Все лоты ---
    if text_lower in ("📈 все лоты", "все лоты", "рынок показать", "рынок"):
        clear_market_browse_state(user_id)
        _show_market_listings_page(player, vk, user_id, 1, None, "newest", None)
        return True

    # --- Категории ---
    cat_mapping = {
        "🔫 оружие": "weapons", "оружие": "weapons", "рынок оружие": "weapons",
        "🛡️ броня": "armor", "броня": "armor", "рынок броня": "armor",
        "💎 артефакты": "artifacts", "артефакты": "artifacts", "рынок артефакты": "artifacts",
        "💊 медицина": "meds", "медицина": "meds", "рынок медицина": "meds",
        "🍖 еда": "food", "еда": "food", "рынок еда": "food",
    }
    if text_lower in cat_mapping:
        _show_market_listings_page(player, vk, user_id, 1, cat_mapping[text_lower], sort, None)
        return True

    # --- Сбросить фильтр ---
    if text_lower in ("✖️ сбросить фильтр", "сбросить фильтр"):
        _show_market_listings_page(player, vk, user_id, 1, None, sort, None)
        return True

    # --- Поиск ---
    if text_lower in ("🔍 поиск", "поиск"):
        vk.messages.send(
            user_id=user_id,
            message="🔍 ПОИСК ПО НАЗВАНИЮ\n\n"
                    "Введи название предмета для поиска.\n"
                    "Например: АК-74, Аптечка, Медуза\n\n"
                    "Нажми «Отмена», чтобы вернуться к списку.",
            keyboard=create_market_search_keyboard().get_keyboard(),
            random_id=0,
        )
        # Атомарно обновляем состояние с флагом поиска
        def updater(s):
            s = s or {}
            s["category"] = category
            s["page"] = page
            s["sort"] = sort
            s["search"] = search
            s["searching"] = True
            return s
        from infra.state_manager import _market_browse_state
        _market_browse_state.update(user_id, updater)
        return True

    # --- Мои лоты ---
    if text_lower in ("🧾 мои лоты", "мои лоты", "мои лот"):
        my_page, my_status = get_market_my_listings_page(user_id)
        show_my_market_listings(player, vk, user_id, page=my_page, status=my_status)
        return True

    # --- Мои сделки ---
    if text_lower in ("📒 мои сделки", "мои сделки", "сделки"):
        show_my_market_transactions(player, vk, user_id)
        return True

    # --- Мои лоты: переключение статуса ---
    if text_lower in ("📋 активные", "активные"):
        set_market_my_listings_page(user_id, page=1, status="active")
        show_my_market_listings(player, vk, user_id, page=1, status="active")
        return True

    if text_lower in ("✅ проданные", "проданные"):
        set_market_my_listings_page(user_id, page=1, status="sold")
        show_my_market_listings(player, vk, user_id, page=1, status="sold")
        return True

    if text_lower in ("📊 все", "все мои лоты", "все мои"):
        set_market_my_listings_page(user_id, page=1, status="all")
        show_my_market_listings(player, vk, user_id, page=1, status="all")
        return True

    # --- Рынок игроков (меню) ---
    if text_lower in ("рынок игроков",):
        clear_market_browse_state(user_id)
        show_market_menu(player, vk, user_id)
        return True

    # --- Купить лот <id> ---
    if handle_market_buy_listing(player, vk, user_id, text):
        return True

    # --- Снять лот <id> ---
    if handle_market_cancel_listing(player, vk, user_id, text):
        return True

    # --- Выставить лот ---
    if handle_market_create_listing(player, vk, user_id, text):
        return True

    return False
