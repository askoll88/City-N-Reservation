"""
P2P рынок игроков (черный рынок)
"""
import re
import time

import config
import database
from handlers.keyboards import (
    create_player_market_keyboard,
    create_purchase_confirm_keyboard,
)
from state_manager import (
    set_pending_purchase,
    clear_pending_purchase,
    has_pending_purchase,
)


def _format_listing(row: dict) -> str:
    return (
        f"#{row['id']} | {row['item_name']} x{row['quantity']}\n"
        f"💵 {row['price_per_item']} руб/шт | Итого: {row['total_price']} руб\n"
        f"🏷️ {row.get('category', 'unknown')} | ✨ {row.get('rarity', 'common')}\n"
        f"👤 Продавец: {row['seller_vk_id']}"
    )


def show_market_menu(player, vk, user_id: int):
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
            "📈 РЫНОК СТАЛКЕРОВ \n\n"
            "Здесь сталкеры торгуют между собой через эскроу.\n"
            "Рынок берет комиссию за безопасность сделки.\n\n"
            "Быстрый старт:\n"
            "1) «Рынок показать» — посмотреть лоты\n"
            "2) «купить лот <id>» — купить\n"
            "3) «выставить <предмет> <цена> [кол-во]» — продать\n\n"
            f"🔒 Доступ с {config.MARKET_MIN_LEVEL} уровня\n"
            f"🧾 Комиссия выставления: {config.MARKET_LISTING_FEE_PCT}%\n"
            f"💸 Комиссия продажи: {config.MARKET_SALE_FEE_PCT}% (с продавца)\n"
            f"📦 Лимит лотов: {config.MARKET_MAX_LISTINGS_PER_USER}\n"
            f"⏱️ Срок лота: {config.MARKET_LISTING_TTL_HOURS}ч\n\n"
            "Команды:\n"
            "• рынок показать\n"
            "• рынок оружие | броня | артефакты | медицина | еда\n"
            "• выставить <предмет> <цена> [кол-во]\n"
            "• купить лот <id>\n"
            "• снять лот <id>\n"
            "• мои лоты\n"
            "• мои сделки"
        ),
        keyboard=create_player_market_keyboard().get_keyboard(),
        random_id=0,
    )


def show_market_listings(player, vk, user_id: int, category: str | None = None):
    listings = database.get_market_listings(limit=12, category=category)
    if not listings:
        vk.messages.send(
            user_id=user_id,
            message="📭 На рынке пока нет подходящих лотов.",
            keyboard=create_player_market_keyboard().get_keyboard(),
            random_id=0,
        )
        return

    lines = ["📈АКТИВНЫЕ ЛОТЫ\n"]
    for row in listings:
        lines.append(_format_listing(row))
        lines.append("")
    lines.append("Чтобы купить: купить лот <id>")

    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines).strip(),
        keyboard=create_player_market_keyboard().get_keyboard(),
        random_id=0,
    )


def show_my_market_listings(player, vk, user_id: int):
    rows = database.get_market_user_listings(user_id, status="active", limit=20)
    if not rows:
        vk.messages.send(
            user_id=user_id,
            message="📭 У тебя нет активных лотов.",
            keyboard=create_player_market_keyboard().get_keyboard(),
            random_id=0,
        )
        return

    lines = ["🧾МОИ АКТИВНЫЕ ЛОТЫ\n"]
    for row in rows:
        lines.append(
            f"#{row['id']} | {row['item_name']} x{row['quantity']} | "
            f"{row['price_per_item']} руб/шт | Итого {row['total_price']} руб"
        )
    lines.append("\nСнять: снять лот <id>")

    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=create_player_market_keyboard().get_keyboard(),
        random_id=0,
    )


def show_my_market_transactions(player, vk, user_id: int):
    rows = database.get_market_user_transactions(user_id, limit=20)
    if not rows:
        vk.messages.send(
            user_id=user_id,
            message="📭 Сделок пока нет.",
            keyboard=create_player_market_keyboard().get_keyboard(),
            random_id=0,
        )
        return

    lines = ["📒МОИ СДЕЛКИ\n"]
    for row in rows:
        side = "🟢 Покупка" if row["buyer_vk_id"] == user_id else "🔵 Продажа"
        lines.append(
            f"{side} | Лот #{row['listing_id']} | {row['item_name']} x{row['quantity']} | "
            f"{row['total_price']} руб"
        )

    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=create_player_market_keyboard().get_keyboard(),
        random_id=0,
    )


def handle_market_create_listing(player, vk, user_id: int, text: str) -> bool:
    m = re.match(r"^выставить\s+(.+?)\s+(\d+)(?:\s+(\d+))?$", text.strip(), flags=re.IGNORECASE)
    if not m:
        return False

    item_name = m.group(1).strip()
    price = int(m.group(2))
    qty = int(m.group(3)) if m.group(3) else 1

    result = database.create_market_listing(user_id, item_name, price, qty)
    vk.messages.send(
        user_id=user_id,
        message=result.get("message", "Не удалось выставить лот."),
        keyboard=create_player_market_keyboard().get_keyboard(),
        random_id=0,
    )
    return True


def handle_market_buy_listing(player, vk, user_id: int, text: str) -> bool:
    """Показать подтверждение покупки вместо мгновенной покупки"""
    m = re.match(r"^купить\s+лот\s+(\d+)$", text.strip(), flags=re.IGNORECASE)
    if not m:
        return False

    # Если уже есть pending покупка — игнорируем
    if has_pending_purchase(user_id):
        vk.messages.send(
            user_id=user_id,
            message="⏳ У тебя уже есть неподтверждённая покупка. Подтверди или отмени её сначала.",
            keyboard=create_purchase_confirm_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    listing_id = int(m.group(1))

    # Получаем информацию о лоте для превью
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

    # Сохраняем pending покупку
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
            f"🛒 <b>ПОДТВЕРЖДЕНИЕ ПОКУПКИ</b>\n\n"
            f"📦 {lot_info['item_name']} x{lot_info['quantity']}\n"
            f"💵 {lot_info['price_per_item']:,} руб/шт\n"
            f"💰 Итого: <b>{total_price:,} руб.</b>\n"
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


def handle_market_confirm_purchase(player, vk, user_id: int, text: str) -> bool:
    """Обработка подтверждения или отмены покупки"""
    if not has_pending_purchase(user_id):
        return False

    text_lower = text.strip().lower()

    # Отмена покупки
    if text_lower in ["❌ отмена", "отмена", "отменить", "нет", "cancel"]:
        pending = get_pending_purchase_data(user_id)
        clear_pending_purchase(user_id)

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

    # Подтверждение покупки
    if text_lower in ["✅ подтвердить", "подтвердить", "подтверждение", "да", "yes", "купить"]:
        pending = get_pending_purchase_data(user_id)
        if not pending:
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

        # Проверяем баланс ещё раз (мог измениться)
        if player.money < total_price:
            clear_pending_purchase(user_id)
            vk.messages.send(
                user_id=user_id,
                message=f"❌ Не хватает денег. Нужно {total_price:,} руб., у тебя {player.money:,} руб.",
                keyboard=create_player_market_keyboard().get_keyboard(),
                random_id=0,
            )
            return True

        # Выполняем покупку через БД
        result = database.buy_market_listing(user_id, listing_id)

        # Очищаем pending независимо от результата
        clear_pending_purchase(user_id)

        if result.get("success"):
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


def get_pending_purchase_data(user_id: int) -> dict | None:
    """Получить данные pending покупки с защитой от stale данных"""
    from state_manager import get_pending_purchase
    data = get_pending_purchase(user_id)
    if not data:
        return None
    # Pending данные истекают через 5 минут
    if time.time() - data.get("start_time", 0) > 300:
        from state_manager import clear_pending_purchase
        clear_pending_purchase(user_id)
        return None
    return data


def handle_market_cancel_listing(player, vk, user_id: int, text: str) -> bool:
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
