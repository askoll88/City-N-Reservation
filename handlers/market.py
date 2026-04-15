"""
P2P рынок игроков (черный рынок)
"""
from __future__ import annotations

import re
import time

import config
import database
from handlers.keyboards import (
    create_player_market_keyboard,
    create_purchase_confirm_keyboard,
    create_market_pagination_keyboard,
    create_market_listing_keyboard,
    create_my_listings_keyboard,
    create_market_search_keyboard,
)
from state_manager import (
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

    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=keyboard.get_keyboard(),
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
            f"⏱️ Срок лота: {config.MARKET_LISTING_TTL_HOURS}ч"
        ),
        keyboard=create_player_market_keyboard().get_keyboard(),
        random_id=0,
    )


def show_market_listings(player, vk, user_id, category=None, page=1, sort="newest", search=None):
    """Показать лоты рынка с пагинацией."""
    _show_market_listings_page(player, vk, user_id, page, category, sort, search)


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
        track_quest_market_list(user_id)
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
            track_quest_market_buy(user_id)
            vk.messages.send(
                user_id=user_id,
                message=f"✅ {result['message']}",
                keyboard=create_player_market_keyboard().get_keyboard(),
                random_id=0,
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

    # --- Режим поиска: пользователь ввёл запрос ---
    if searching:
        clear_market_browse_state(user_id)
        _show_market_listings_page(player, vk, user_id, 1, None, "newest", text.strip())
        return True

    # --- Навигация по страницам ---
    if text_lower in ("◀️ назад", "назад") and page > 1:
        _show_market_listings_page(player, vk, user_id, page - 1, category, sort, search)
        return True

    if text_lower in ("▶️ вперёд", "вперёд") and page < 999:
        _show_market_listings_page(player, vk, user_id, page + 1, category, sort, search)
        return True

    # Номер страницы
    if text_lower.isdigit():
        p = int(text_lower)
        if 1 <= p <= 999:
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
                    "Или нажми «Отмена» чтобы выйти.",
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
        from state_manager import _market_browse_state
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
