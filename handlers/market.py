"""
P2P рынок игроков (черный рынок)
"""
import re

import config
import database
from handlers.keyboards import create_player_market_keyboard


def _format_listing(row: dict) -> str:
    return (
        f"#{row['id']} | {row['item_name']} x{row['quantity']}\n"
        f"💵 {row['price_per_item']} руб/шт | Итого: {row['total_price']} руб\n"
        f"🏷️ {row.get('category', 'unknown')} | ✨ {row.get('rarity', 'common')}\n"
        f"👤 Продавец: {row['seller_vk_id']}"
    )


def show_market_menu(player, vk, user_id: int):
    vk.messages.send(
        user_id=user_id,
        message=(
            "📈 <b>РЫНОК СТАЛКЕРОВ</b>\n\n"
            "Здесь сталкеры торгуют между собой через эскроу.\n"
            "Рынок берет комиссию за безопасность сделки.\n\n"
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

    lines = ["📈 <b>АКТИВНЫЕ ЛОТЫ</b>\n"]
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

    lines = ["🧾 <b>МОИ АКТИВНЫЕ ЛОТЫ</b>\n"]
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

    lines = ["📒 <b>МОИ СДЕЛКИ</b>\n"]
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
    m = re.match(r"^купить\s+лот\s+(\d+)$", text.strip(), flags=re.IGNORECASE)
    if not m:
        return False

    listing_id = int(m.group(1))
    result = database.buy_market_listing(user_id, listing_id)
    vk.messages.send(
        user_id=user_id,
        message=result.get("message", "Не удалось купить лот."),
        keyboard=create_player_market_keyboard().get_keyboard(),
        random_id=0,
    )
    return True


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
