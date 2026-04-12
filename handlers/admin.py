"""
Админские команды для управления игрой
"""
import re

import database
from handlers.keyboards import create_admin_keyboard


def _send(vk, user_id: int, message: str):
    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=create_admin_keyboard().get_keyboard(),
        random_id=0,
    )


def _help_text() -> str:
    return (
        "🛠️ <b>АДМИНКА</b>\n\n"
        "Пользователи:\n"
        "• админ пользователи [поиск]\n"
        "• админ профиль <vk_id>\n"
        "• админ права <vk_id> on|off\n\n"
        "Баны:\n"
        "• бан <vk_id> [причина]\n"
        "• разбан <vk_id>\n"
        "• админ баны\n\n"
        "Предметы/статы:\n"
        "• админ выдать <vk_id> <кол-во> <предмет>\n"
        "• админ set <vk_id> <поле> <значение>\n"
        "  поля: money, level, experience, health, energy,\n"
        "        radiation, strength, stamina, perception,\n"
        "        luck, shells, artifact_slots, max_weight\n\n"
        "Маркет:\n"
        "• админ маркет on|off\n"
        "• админ лоты [active|sold|cancelled|expired|all]\n"
        "• админ снять лот <id>\n"
    )


def handle_admin_commands(player, vk, user_id: int, text: str, original_text: str = "") -> bool:
    text = (text or "").strip().lower()
    original_text = (original_text or "").strip()

    admin_triggers = (
        text.startswith("админ")
        or text.startswith("бан ")
        or text.startswith("разбан ")
        or text in {
            "админка",
            "admin",
            "админ: пользователи",
            "админ: баны",
            "админ: маркет on",
            "админ: маркет off",
            "админ: лоты",
            "админ: помощь",
        }
    )
    if not admin_triggers:
        return False

    if not database.is_user_admin(user_id):
        vk.messages.send(
            user_id=user_id,
            message="⛔ Нет доступа к админ-командам.",
            random_id=0,
        )
        return True

    if text in {"админка", "admin", "админ", "админ: помощь"}:
        _send(vk, user_id, _help_text())
        return True

    if text in {"админ: пользователи", "админ пользователи", "админ юзеры"}:
        users = database.admin_search_users(limit=20)
        if not users:
            _send(vk, user_id, "Пользователи не найдены.")
            return True
        lines = ["👥 <b>ПОСЛЕДНИЕ ПОЛЬЗОВАТЕЛИ</b>\n"]
        for u in users:
            flags = []
            if u.get("is_admin"):
                flags.append("admin")
            if u.get("is_banned"):
                flags.append("banned")
            f = f" [{' '.join(flags)}]" if flags else ""
            lines.append(f"{u['vk_id']} | {u['name']} | lvl {u['level']} | {u['money']} руб{f}")
        _send(vk, user_id, "\n".join(lines))
        return True

    m = re.match(r"^админ\s+пользователи\s+(.+)$", original_text, flags=re.IGNORECASE)
    if m:
        query = m.group(1).strip()
        users = database.admin_search_users(query=query, limit=20)
        lines = [f"🔎 <b>ПОИСК: {query}</b>\n"]
        for u in users:
            lines.append(f"{u['vk_id']} | {u['name']} | lvl {u['level']} | {u['money']} руб")
        if len(lines) == 1:
            lines.append("Ничего не найдено.")
        _send(vk, user_id, "\n".join(lines))
        return True

    m = re.match(r"^админ\s+профиль\s+(\d+)$", text)
    if m:
        target = int(m.group(1))
        user = database.get_admin_user(target)
        if not user:
            _send(vk, user_id, "Пользователь не найден.")
            return True
        _send(
            vk,
            user_id,
            (
                f"🧾 <b>ПРОФИЛЬ {user['vk_id']}</b>\n\n"
                f"Имя: {user['name']}\n"
                f"Локация: {user['location']}\n"
                f"Уровень: {user['level']}\n"
                f"Деньги: {user['money']}\n"
                f"Админ: {user['is_admin']}\n"
                f"Бан: {user['is_banned']}\n"
                f"Причина: {user.get('ban_reason') or '-'}"
            ),
        )
        return True

    m = re.match(r"^админ\s+права\s+(\d+)\s+(on|off)$", text)
    if m:
        target = int(m.group(1))
        mode = m.group(2)
        result = database.set_user_admin(target, is_admin=(mode == "on"))
        _send(vk, user_id, result["message"])
        return True

    m = re.match(r"^бан\s+(\d+)(?:\s+(.+))?$", original_text, flags=re.IGNORECASE)
    if m:
        target = int(m.group(1))
        reason = m.group(2).strip() if m.group(2) else "без причины"
        result = database.set_user_ban(target, True, reason)
        _send(vk, user_id, result["message"])
        return True

    m = re.match(r"^разбан\s+(\d+)$", text)
    if m:
        target = int(m.group(1))
        result = database.set_user_ban(target, False, None)
        _send(vk, user_id, result["message"])
        return True

    if text in {"админ: баны", "админ баны"}:
        bans = database.admin_list_banned_users(limit=50)
        if not bans:
            _send(vk, user_id, "✅ Активных банов нет.")
            return True
        lines = ["⛔ <b>ЗАБАНЕННЫЕ ПОЛЬЗОВАТЕЛИ</b>\n"]
        for b in bans:
            lines.append(f"{b['vk_id']} | {b['name']} | {b.get('ban_reason') or '-'}")
        _send(vk, user_id, "\n".join(lines))
        return True

    m = re.match(r"^админ\s+выдать\s+(\d+)\s+(\d+)\s+(.+)$", original_text, flags=re.IGNORECASE)
    if m:
        target = int(m.group(1))
        qty = int(m.group(2))
        item_name = m.group(3).strip()
        result = database.admin_give_item(target, item_name, qty)
        _send(vk, user_id, result["message"])
        return True

    m = re.match(r"^админ\s+set\s+(\d+)\s+([a-z_]+)\s+(-?\d+)$", text)
    if m:
        target = int(m.group(1))
        field = m.group(2)
        value = int(m.group(3))
        result = database.admin_set_user_field(target, field, value)
        _send(vk, user_id, result["message"])
        return True

    if text in {"админ: маркет on", "админ маркет on"}:
        database.set_game_setting("p2p_market_enabled", "1")
        _send(vk, user_id, "✅ P2P рынок включён.")
        return True

    if text in {"админ: маркет off", "админ маркет off"}:
        database.set_game_setting("p2p_market_enabled", "0")
        _send(vk, user_id, "⛔ P2P рынок отключён.")
        return True

    m = re.match(r"^админ\s+лоты(?:\s+(active|sold|cancelled|expired|all))?$", text)
    if m:
        status = m.group(1) or "active"
        rows = database.admin_get_market_listings(status=status, limit=30)
        if not rows:
            _send(vk, user_id, f"Лотов со статусом '{status}' нет.")
            return True
        lines = [f"🧾 <b>ЛОТЫ ({status})</b>\n"]
        for r in rows:
            lines.append(
                f"#{r['id']} | {r['item_name']} x{r['quantity']} | {r['price_per_item']} руб | "
                f"{r['status']} | seller={r['seller_vk_id']}"
            )
        _send(vk, user_id, "\n".join(lines))
        return True

    if text in {"админ: лоты"}:
        rows = database.admin_get_market_listings(status="active", limit=30)
        lines = ["🧾 <b>АКТИВНЫЕ ЛОТЫ</b>\n"]
        for r in rows:
            lines.append(
                f"#{r['id']} | {r['item_name']} x{r['quantity']} | {r['price_per_item']} руб | seller={r['seller_vk_id']}"
            )
        if len(lines) == 1:
            lines.append("Нет лотов.")
        _send(vk, user_id, "\n".join(lines))
        return True

    m = re.match(r"^админ\s+снять\s+лот\s+(\d+)$", text)
    if m:
        listing_id = int(m.group(1))
        result = database.admin_cancel_market_listing(listing_id)
        _send(vk, user_id, result["message"])
        return True

    _send(vk, user_id, _help_text())
    return True
