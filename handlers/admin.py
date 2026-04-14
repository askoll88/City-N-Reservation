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
        "🛠️АДМИНКА\n\n"
        "Пользователи:\n"
        "• админ пользователи [поиск]\n"
        "• админ профиль <vk_id>\n"
        "• админ права <vk_id> on|off\n"
        "• админ инвентарь <vk_id>\n"
        "• админ локация <vk_id> <локация>\n\n"
        "Баны:\n"
        "• бан <vk_id> [причина]\n"
        "• разбан <vk_id>\n"
        "• админ баны\n\n"
        "Предметы/статы:\n"
        "• админ выдать <vk_id> <кол-во> <предмет>\n"
        "• админ удалить <vk_id> <предмет> [кол-во]\n"
        "• админ set <vk_id> <поле> <значение>\n"
        "  поля: money, level, experience, health, energy,\n"
        "        radiation, strength, stamina, perception,\n"
        "        luck, shells, artifact_slots, max_weight\n\n"
        "Маркет:\n"
        "• админ маркет on|off\n"
        "• админ лоты [active|sold|cancelled|expired|all]\n"
        "• админ снять лот <id>\n\n"
        "Выброс:\n"
        "• админ выброс — запустить выброс\n"
        "• админ выброс отмена — отменить выброс\n"
        "• админ выброс статус — статистика\n\n"
        "Квесты/События:\n"
        "• админ квесты <vk_id> — ежедневные квесты\n"
        "• админ рандом <vk_id> — принудительно дать рандом ивент\n"
        "• админ кулдаун <vk_id> снять — снять кулдаун событий\n"
        "• админ кулдаун <vk_id> инфо — показать кулдаун\n\n"
        "Онлайн:\n"
        "• админ онлайн — статистика игроков\n"
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
            "админ: выброс",
            "админ: выброс статус",
            "админ: выброс отмена",
            "админ: онлайн",
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
        lines = ["👥ПОСЛЕДНИЕ ПОЛЬЗОВАТЕЛИ\n"]
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
        lines = [f"🔎ПОИСК: {query}\n"]
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
                f"🧾ПРОФИЛЬ {user['vk_id']}\n\n"
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
        lines = ["⛔ЗАБАНЕННЫЕ ПОЛЬЗОВАТЕЛИ\n"]
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
        lines = [f"🧾ЛОТЫ ({status})\n"]
        for r in rows:
            lines.append(
                f"#{r['id']} | {r['item_name']} x{r['quantity']} | {r['price_per_item']} руб | "
                f"{r['status']} | seller={r['seller_vk_id']}"
            )
        _send(vk, user_id, "\n".join(lines))
        return True

    if text in {"админ: лоты"}:
        rows = database.admin_get_market_listings(status="active", limit=30)
        lines = ["🧾АКТИВНЫЕ ЛОТЫ\n"]
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

    # === Выброс ===
    if text in {"админ: выброс", "админ выброс"}:
        from emission import schedule_admin_emission
        try:
            emission_id = schedule_admin_emission(vk)
            _send(
                vk, user_id,
                f"☢️ **Выброс запущен!**\n\n"
                f"ID: {emission_id}\n"
                f"Предупреждение отправлено всем игрокам в Зоне.\n"
                f"Удар через 15 минут."
            )
        except Exception as e:
            _send(vk, user_id, f"❌ Ошибка при запуске выброса: {e}")
        return True

    if text in {"админ: выброс статус", "админ выброс статус"}:
        stats = database.get_emission_stats()
        if not stats or stats.get("total_emissions", 0) == 0:
            _send(vk, user_id, "📊 Выбросов ещё не было.")
        else:
            _send(
                vk, user_id,
                f"📊 **Статистика выбросов:**\n\n"
                f"Всего: {stats['total_emissions']}\n"
                f"Активных: {stats['active_emissions']}\n"
                f"Админских: {stats['admin_triggered']}\n"
                f"Последний: {stats['last_emission'] or '-'}"
            )
        return True

    if text in {"админ: выброс отмена", "админ выброс отмена"}:
        from emission import EMISSION_PHASE_PENDING, EMISSION_PHASE_WARNING, EMISSION_PHASE_IMPACT
        emission = database.get_active_emission()
        if not emission:
            _send(vk, user_id, "ℹ️ Нет активного выброса.")
            return True
        if emission["status"] == EMISSION_PHASE_IMPACT:
            _send(vk, user_id, "❌ Нельзя отменить — выброс уже бьёт!")
            return True
        database.update_emission_status(emission["id"], "cancelled")
        _send(vk, user_id, f"✅ Выброс #{emission['id']} отменён.")
        return True

    # === Квесты игрока ===
    m = re.match(r"^админ\s+квесты\s+(\d+)$", text)
    if m:
        target = int(m.group(1))
        user = database.get_admin_user(target)
        if not user:
            _send(vk, user_id, "Пользователь не найден.")
            return True

        quests_info = database.get_daily_quests_for_user(target)
        if not quests_info:
            _send(vk, user_id, f"📋 Квесты игрока {user['name']}:\n\nЕжедневных квестов нет.")
            return True

        lines = [f"📋 КВЕСТЫ: {user['name']} (vk:{target})\n"]
        lines.append(f"Стрик: {quests_info['streak']} дней")
        lines.append(f"Claimed: {'да' if quests_info['claimed'] else 'нет'}\n")

        for i, q in enumerate(quests_info.get("quests", []), 1):
            qid = q["id"]
            qtype = q.get("type", "?")
            progress = quests_info.get("progress", {}).get(qid, 0)
            target_val = q.get("target", "?")
            reward = q.get("reward_xp", 0)
            lines.append(
                f"{i}. [{qtype}] {progress}/{target_val} → XP:{reward}"
            )

        _send(vk, user_id, "\n".join(lines))
        return True

    # === Принудительный рандом ивент ===
    m = re.match(r"^админ\s+рандом\s+(\d+)$", text)
    if m:
        target = int(m.group(1))
        from state_manager import has_pending_event, clear_pending_event, set_pending_event
        from random_events import get_random_event, format_event_message
        from handlers.keyboards import create_random_event_keyboard

        if has_pending_event(target):
            clear_pending_event(target)

        event = get_random_event(user_id=target)
        if not event:
            _send(vk, user_id, f"❌ Рандомное событие для vk:{target} не сгенерировалось. Попробуй ещё раз.")
            return True

        set_pending_event(target, event)
        try:
            vk.messages.send(
                user_id=target,
                message=f"🎲 **АДМИНСКИЙ ИВЕНТ**\n\n{format_event_message(event)}",
                keyboard=create_random_event_keyboard(event).get_keyboard(),
                random_id=0,
            )
            _send(vk, user_id, f"✅ Рандомный ивент отправлен игроку vk:{target}\nТип: {event.get('type', '?')}")
        except Exception as e:
            _send(vk, user_id, f"❌ Ошибка: {e}")
        return True

    # === Кулдаун событий ===
    m = re.match(r"^админ\s+кулдаун\s+(\d+)\s+(снять|инфо)$", text)
    if m:
        target = int(m.group(1))
        action = m.group(2)

        user = database.get_admin_user(target)
        if not user:
            _send(vk, user_id, "Пользователь не найден.")
            return True

        import time
        last_time = database.get_user_flag(target, "last_random_event_time", 0)

        if action == "инфо":
            if last_time == 0:
                _send(vk, user_id, f"⏰ Кулдаун игрока {user['name']}:\n\nСобытий ещё не было.")
            else:
                elapsed = int(time.time()) - last_time
                mins = elapsed // 60
                if elapsed < 15 * 60:
                    remaining = 15 * 60 - elapsed
                    _send(
                        vk, user_id,
                        f"⏰ Кулдаун игрока {user['name']}:\n\n"
                        f"Последнее событие: {mins} мин назад\n"
                        f"⏳ Осталось: {remaining // 60} мин"
                    )
                else:
                    after_cooldown = elapsed - 15 * 60
                    intervals = after_cooldown // (10 * 60)
                    chance = min(100, intervals * 1.5)
                    _send(
                        vk, user_id,
                        f"⏰ Кулдаун игрока {user['name']}:\n\n"
                        f"Последнее событие: {mins} мин назад\n"
                        f"✅ Кулдаун прошёл\n"
                        f"🎲 Шанс нового события: {chance:.1f}%"
                    )
            return True

        if action == "снять":
            database.set_user_flag(target, "last_random_event_time", 0)
            _send(vk, user_id, f"✅ Кулдаун событий сброшен для {user['name']}.")
            return True

    # === Инвентарь игрока ===
    m = re.match(r"^админ\s+инвентарь\s+(\d+)$", text)
    if m:
        target = int(m.group(1))
        user = database.get_admin_user(target)
        if not user:
            _send(vk, user_id, "Пользователь не найден.")
            return True

        inventory = database.get_user_inventory(target)
        if not inventory:
            _send(vk, user_id, f"🎒 Инвентарь {user['name']}:\n\nПусто.")
            return True

        lines = [f"🎒 ИНВЕНТАРЬ: {user['name']} (vk:{target})\n"]
        for item in inventory:
            lines.append(
                f"• {item['name']} x{item['quantity']} "
                f"(цена:{item['price']} урон:{item.get('attack', 0)} защ:{item.get('defense', 0)})"
            )
        _send(vk, user_id, "\n".join(lines))
        return True

    # === Сменить локацию игроку ===
    m = re.match(r"^админ\s+локация\s+(\d+)\s+(.+)$", text)
    if m:
        target = int(m.group(1))
        new_location = m.group(2).strip()

        from constants import LocationType
        valid_locations = {loc.value for loc in LocationType}
        if new_location not in valid_locations:
            _send(
                vk, user_id,
                f"❌ Неверная локация. Доступные: {', '.join(sorted(valid_locations))}"
            )
            return True

        database.update_user_location(target, new_location)
        user = database.get_admin_user(target)
        _send(vk, user_id, f"✅ {user['name']} перемещён в '{new_location}'.")
        return True

    # === Удалить предмет ===
    m = re.match(r"^админ\s+удалить\s+(\d+)\s+(.+?)(?:\s+(\d+))?$", original_text, flags=re.IGNORECASE)
    if m:
        target = int(m.group(1))
        item_name = m.group(2).strip()
        qty = int(m.group(3)) if m.group(3) else 1

        result = database.admin_remove_item(target, item_name, qty)
        user = database.get_admin_user(target)
        if result:
            _send(vk, user_id, f"✅ Удалено {qty}x '{item_name}' у {user['name']}.")
        else:
            _send(vk, user_id, f"❌ Предмет не найден или ошибка.")
        return True

    # === Статистика онлайн ===
    if text in {"админ: онлайн", "админ онлайн"}:
        all_players = database.get_all_active_players()
        total = len(all_players)

        # Считаем по локациям
        location_counts = {}
        for p in all_players:
            loc = p.get("location", "неизвестно")
            location_counts[loc] = location_counts.get(loc, 0) + 1

        # Считаем по уровням
        lvl_ranges = {"1-5": 0, "6-10": 0, "11-20": 0}
        for p in all_players:
            lvl = p.get("level", 1)
            if lvl <= 5:
                lvl_ranges["1-5"] += 1
            elif lvl <= 10:
                lvl_ranges["6-10"] += 1
            else:
                lvl_ranges["11-20"] += 1

        lines = [f"👥 СТАТИСТИКА ИГРОКОВ\n"]
        lines.append(f"Всего: {total}")
        lines.append("\nПо уровням:")
        for rng, count in lvl_ranges.items():
            lines.append(f"  {rng}: {count}")
        lines.append("\nПо локациям:")
        for loc, count in sorted(location_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {loc}: {count}")

        _send(vk, user_id, "\n".join(lines))
        return True

    _send(vk, user_id, _help_text())
    return True
