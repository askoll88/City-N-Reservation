"""
Админские команды для управления игрой — с подменю и кнопками
"""
import re
import time

import database
from handlers.keyboards import (
    create_admin_keyboard,
    create_admin_users_keyboard,
    create_admin_emission_keyboard,
    create_admin_give_keyboard,
    create_admin_events_keyboard,
    create_admin_market_keyboard,
    create_admin_help_keyboard,
)
import database


def _set_admin_menu(user_id: int, category: str):
    # Храним как строку: 1=users, 2=emission, 3=give, 4=events, 5=market, 6=help
    codes = {"users": 1, "emission": 2, "give": 3, "events": 4, "market": 5, "help": 6}
    database.set_user_flag(user_id, "_admin_menu", codes.get(category, 0))


def _get_admin_menu(user_id: int) -> str | None:
    val = database.get_user_flag(user_id, "_admin_menu", 0)
    if val == 0:
        return None
    mapping = {1: "users", 2: "emission", 3: "give", 4: "events", 5: "market", 6: "help"}
    return mapping.get(val)


def _clear_admin_menu(user_id: int):
    database.set_user_flag(user_id, "_admin_menu", 0)


def _send(vk, user_id: int, message: str, keyboard=None):
    if keyboard is None:
        keyboard = create_admin_keyboard()
    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=keyboard.get_keyboard(),
        random_id=0,
    )


def _show_main_menu(vk, user_id: int):
    _clear_admin_menu(user_id)
    _send(vk, user_id, "🛠️ **АДМИН-ПАНЕЛЬ**\n\nВыбери категорию:", create_admin_keyboard())


def _show_category(vk, user_id: int, category: str):
    _set_admin_menu(user_id, category)
    keyboards = {
        "users": create_admin_users_keyboard(),
        "emission": create_admin_emission_keyboard(),
        "give": create_admin_give_keyboard(),
        "events": create_admin_events_keyboard(),
        "market": create_admin_market_keyboard(),
        "help": create_admin_help_keyboard(),
    }
    kb = keyboards.get(category, create_admin_keyboard())
    titles = {
        "users": "👥 **ПОЛЬЗОВАТЕЛИ**\n\nВыбери действие:",
        "emission": "☢️ **ВЫБРОС**\n\nУправление глобальным событием:",
        "give": "📦 **ВЫДАЧА**\n\nВыдача/удаление предметов и статов:",
        "events": "🎲 **ИВЕНТЫ**\n\nУправление событиями и квестами:",
        "market": "🏪 **МАРКЕТ**\n\nУправление P2P рынком:",
        "help": "📖 **СПРАВКА АДМИНА**\n\nВсе команды начинаются с `админ`:\n"
                "• `админ пользователи [поиск]` — список/поиск\n"
                "• `админ профиль <vk_id>` — профиль\n"
                "• `админ права <vk_id> on|off` — права\n"
                "• `админ выдать <vk_id> <кол-во> <предмет>`\n"
                "• `админ удалить <vk_id> <предмет> [кол-во]`\n"
                "• `админ set <vk_id> <поле> <значение>`\n"
                "  поля: money, level, experience, health, energy,\n"
                "  radiation, strength, stamina, perception, luck,\n"
                "  shells, artifact_slots, max_weight\n"
                "• `бан <vk_id> [причина]`\n"
                "• `разбан <vk_id>`\n"
                "• `админ маркет on|off`\n"
                "• `админ лоты [active|sold|cancelled|expired|all]`\n"
                "• `админ снять лот <id>`\n"
                "• `админ квесты <vk_id>`\n"
                "• `админ рандом <vk_id>`\n"
                "• `админ кулдаун <vk_id> снять|инфо`\n"
                "• `админ инвентарь <vk_id>`\n"
                "• `админ локация <vk_id> <локация>`\n"
                "• `админ онлайн`\n",
    }
    _send(vk, user_id, titles.get(category, "Выбери категорию:"), kb)


def handle_admin_commands(player, vk, user_id: int, text: str, original_text: str = "") -> bool:
    text = (text or "").strip().lower()
    original_text = (original_text or "").strip()

    # Админ — всегда ловим. Если в подменю — любое сообщение.
    # Если нет подменю — проверяем триггеры.
    if not _get_admin_menu(user_id):
        if not (text.startswith("админ")
                or text.startswith("бан ")
                or text.startswith("разбан ")
                or text in {"админка", "admin", "админ",
                            "👥 пользователи", "☢️ выброс", "📦 выдача",
                            "🎲 ивенты", "🏪 маркет", "❓ помощь",
                            "последние пользователи", "забаненные",
                            "профиль (по vk_id)", "инвентарь (по vk_id)",
                            "права on/off", "локация (телепорт)",
                            "☢️ запустить выброс", "⛔ отменить выброс", "📊 статус выброса",
                            "🎁 выдать предмет", "🗑️ удалить предмет", "📝 set поле (статы)",
                            "🎲 рандом ивент игроку", "📋 квесты игрока",
                            "⏰ кулдаун инфо", "⏰ кулдаун снять", "👥 онлайн",
                            "📋 активные лоты", "🗂️ все лоты",
                            "✅ маркет on", "⛔ маркет off", "✖️ снять лот",
                            "⬅️ назад"}):
            return False

    if not database.is_user_admin(user_id):
        vk.messages.send(user_id=user_id, message="⛔ Нет доступа к админ-командам.", random_id=0)
        return True

    # === Кнопки главного меню ===
    if text in {"👥 пользователи", "пользователи"}:
        _show_category(vk, user_id, "users"); return True
    if text in {"☢️ выброс", "выброс"}:
        _show_category(vk, user_id, "emission"); return True
    if text in {"📦 выдача", "выдача"}:
        _show_category(vk, user_id, "give"); return True
    if text in {"🎲 ивенты", "ивенты"}:
        _show_category(vk, user_id, "events"); return True
    if text in {"🏪 маркет", "маркет"}:
        _show_category(vk, user_id, "market"); return True
    if text in {"❓ помощь", "помощь", "админка", "admin", "админ"}:
        _show_main_menu(vk, user_id); return True

    # === Кнопка "Назад" из подменю ===
    if text in {"⬅️ назад", "назад"} and _get_admin_menu(user_id):
        _show_main_menu(vk, user_id); return True

    # === Кнопки: Пользователи ===
    if text == "последние пользователи":
        users = database.admin_search_users(limit=20)
        if not users:
            _send(vk, user_id, "Пользователи не найдены.", create_admin_users_keyboard()); return True
        lines = ["👥 ПОСЛЕДНИЕ ПОЛЬЗОВАТЕЛИ\n"]
        for u in users:
            flags = []
            if u.get("is_admin"): flags.append("admin")
            if u.get("is_banned"): flags.append("banned")
            lines.append(f"{u['vk_id']} | {u['name']} | lvl {u['level']} | {u['money']} руб{' [' + ' '.join(flags) + ']' if flags else ''}")
        _send(vk, user_id, "\n".join(lines), create_admin_users_keyboard()); return True

    if text == "забаненные":
        bans = database.admin_list_banned_users(limit=50)
        if not bans:
            _send(vk, user_id, "✅ Активных банов нет.", create_admin_users_keyboard()); return True
        lines = ["⛔ ЗАБАНЕННЫЕ\n"]
        for b in bans:
            lines.append(f"{b['vk_id']} | {b['name']} | {b.get('ban_reason') or '-'}")
        _send(vk, user_id, "\n".join(lines), create_admin_users_keyboard()); return True

    if text == "профиль (по vk_id)":
        _send(vk, user_id, "Введи:\n`админ профиль <vk_id>`", create_admin_users_keyboard()); return True
    if text == "инвентарь (по vk_id)":
        _send(vk, user_id, "Введи:\n`админ инвентарь <vk_id>`", create_admin_users_keyboard()); return True
    if text == "права on/off":
        _send(vk, user_id, "Введи:\n`админ права <vk_id> on` / `off`", create_admin_users_keyboard()); return True
    if text == "локация (телепорт)":
        _send(vk, user_id, "Введи:\n`админ локация <vk_id> <локация>`\n\nгород, кпп, больница, черный рынок, убежище, дорога_военная_часть, дорога_нии, дорога_зараженный_лес", create_admin_users_keyboard()); return True

    # === Кнопки: Выброс ===
    if text == "☢️ запустить выброс":
        from emission import schedule_admin_emission
        try:
            eid = schedule_admin_emission(vk)
            _send(vk, user_id, f"☢️ Выброс запущен!\n\nID: {eid}\nПредупреждение отправлено.\nУдар через 15 мин.", create_admin_emission_keyboard())
        except Exception as e:
            _send(vk, user_id, f"❌ Ошибка: {e}", create_admin_emission_keyboard())
        return True

    if text == "⛔ отменить выброс":
        from emission import EMISSION_PHASE_IMPACT, EMISSION_PHASE_CANCELLED, _announce_emission_cancelled
        emission = database.get_active_emission()
        if not emission:
            _send(vk, user_id, "ℹ️ Нет активного выброса.", create_admin_emission_keyboard()); return True
        if emission["status"] == EMISSION_PHASE_IMPACT:
            _send(vk, user_id, "❌ Нельзя отменить — выброс уже бьёт!", create_admin_emission_keyboard()); return True
        # Сначала оповещаем игроков, потом обновляем статус
        _announce_emission_cancelled(vk, emission["id"])
        database.update_emission_status(emission["id"], EMISSION_PHASE_CANCELLED)
        _send(vk, user_id, f"✅ Выброс #{emission['id']} отменён. Игрокам отправлено оповещение.", create_admin_emission_keyboard()); return True

    if text == "📊 статус выброса":
        stats = database.get_emission_stats()
        if not stats or stats.get("total_emissions", 0) == 0:
            _send(vk, user_id, "📊 Выбросов ещё не было.", create_admin_emission_keyboard()); return True
        _send(vk, user_id, f"📊 **Выбросы**\n\nВсего: {stats['total_emissions']}\nАктивных: {stats['active_emissions']}\nАдминских: {stats['admin_triggered']}\nПоследний: {stats['last_emission'] or '-'}", create_admin_emission_keyboard()); return True

    # === Кнопки: Выдача ===
    if text == "🎁 выдать предмет":
        _send(vk, user_id, "Введи:\n`админ выдать <vk_id> <кол-во> <предмет>`\n\nПример: `админ выдать 123456 5 Аптечка`", create_admin_give_keyboard()); return True
    if text == "🗑️ удалить предмет":
        _send(vk, user_id, "Введи:\n`админ удалить <vk_id> <предмет> [кол-во]`\n\nПример: `админ удалить 123456 Мутаген`", create_admin_give_keyboard()); return True
    if text == "📝 set поле (статы)":
        _send(vk, user_id, "Введи:\n`админ set <vk_id> <поле> <значение>`\n\nПоля: money, level, experience, health, energy, radiation, strength, stamina, perception, luck, shells, artifact_slots, max_weight", create_admin_give_keyboard()); return True

    # === Кнопки: Ивенты ===
    if text == "🎲 рандом ивент игроку":
        _send(vk, user_id, "Введи:\n`админ рандом <vk_id>`", create_admin_events_keyboard()); return True
    if text == "📋 квесты игрока":
        _send(vk, user_id, "Введи:\n`админ квесты <vk_id>`", create_admin_events_keyboard()); return True
    if text == "⏰ кулдаун инфо":
        _send(vk, user_id, "Введи:\n`админ кулдаун <vk_id> инфо`", create_admin_events_keyboard()); return True
    if text == "⏰ кулдаун снять":
        _send(vk, user_id, "Введи:\n`админ кулдаун <vk_id> снять`", create_admin_events_keyboard()); return True

    if text == "👥 онлайн":
        all_players = database.get_all_active_players()
        total = len(all_players)
        location_counts = {}
        for p in all_players:
            loc = p.get("location", "неизвестно")
            location_counts[loc] = location_counts.get(loc, 0) + 1
        lvl_ranges = {"1-5": 0, "6-10": 0, "11-20": 0}
        for p in all_players:
            lvl = p.get("level", 1)
            if lvl <= 5: lvl_ranges["1-5"] += 1
            elif lvl <= 10: lvl_ranges["6-10"] += 1
            else: lvl_ranges["11-20"] += 1
        lines = [f"👥 СТАТИСТИКА ИГРОКОВ\n"]
        lines.append(f"Всего: {total}")
        lines.append("\nПо уровням:")
        for rng, count in lvl_ranges.items():
            lines.append(f"  {rng}: {count}")
        lines.append("\nПо локациям:")
        for loc, count in sorted(location_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {loc}: {count}")
        _send(vk, user_id, "\n".join(lines), create_admin_events_keyboard()); return True

    # === Кнопки: Маркет ===
    if text == "📋 активные лоты":
        rows = database.admin_get_market_listings(status="active", limit=30)
        if not rows:
            _send(vk, user_id, "Активных лотов нет.", create_admin_market_keyboard()); return True
        lines = ["🧾 АКТИВНЫЕ ЛОТЫ\n"]
        for r in rows:
            lines.append(f"#{r['id']} | {r['item_name']} x{r['quantity']} | {r['price_per_item']} руб | seller={r['seller_vk_id']}")
        _send(vk, user_id, "\n".join(lines), create_admin_market_keyboard()); return True
    if text == "🗂️ все лоты":
        _send(vk, user_id, "Введи:\n`админ лоты [active|sold|cancelled|expired|all]`", create_admin_market_keyboard()); return True
    if text == "✅ маркет on":
        database.set_game_setting("p2p_market_enabled", "1")
        _send(vk, user_id, "✅ P2P рынок включён.", create_admin_market_keyboard()); return True
    if text == "⛔ маркет off":
        database.set_game_setting("p2p_market_enabled", "0")
        _send(vk, user_id, "⛔ P2P рынок отключён.", create_admin_market_keyboard()); return True
    if text == "✖️ снять лот":
        _send(vk, user_id, "Введи:\n`админ снять лот <id>`", create_admin_market_keyboard()); return True

    # === Текстовые команды (работают из любого состояния) ===
    m = re.match(r"^админ\s+пользователи\s+(.+)$", original_text, flags=re.IGNORECASE)
    if m:
        query = m.group(1).strip()
        users = database.admin_search_users(query=query, limit=20)
        lines = [f"🔎 ПОИСК: {query}\n"]
        for u in users:
            lines.append(f"{u['vk_id']} | {u['name']} | lvl {u['level']} | {u['money']} руб")
        if len(lines) == 1: lines.append("Ничего не найдено.")
        _send(vk, user_id, "\n".join(lines)); return True

    m = re.match(r"^админ\s+профиль\s+(\d+)$", text)
    if m:
        target = int(m.group(1))
        user = database.get_admin_user(target)
        if not user:
            _send(vk, user_id, "Пользователь не найден."); return True
        _send(vk, user_id, f"🧾 ПРОФИЛЬ {user['vk_id']}\n\nИмя: {user['name']}\nЛокация: {user['location']}\nУровень: {user['level']}\nДеньги: {user['money']}\nАдмин: {user['is_admin']}\nБан: {user['is_banned']}\nПричина: {user.get('ban_reason') or '-'}"); return True

    m = re.match(r"^админ\s+права\s+(\d+)\s+(on|off)$", text)
    if m:
        result = database.set_user_admin(int(m.group(1)), is_admin=(m.group(2) == "on"))
        _send(vk, user_id, result["message"]); return True

    m = re.match(r"^бан\s+(\d+)(?:\s+(.+))?$", original_text, flags=re.IGNORECASE)
    if m:
        result = database.set_user_ban(int(m.group(1)), True, (m.group(2) or "без причины").strip())
        _send(vk, user_id, result["message"]); return True

    m = re.match(r"^разбан\s+(\d+)$", text)
    if m:
        result = database.set_user_ban(int(m.group(1)), False, None)
        _send(vk, user_id, result["message"]); return True

    m = re.match(r"^админ\s+выдать\s+(\d+)\s+(\d+)\s+(.+)$", original_text, flags=re.IGNORECASE)
    if m:
        result = database.admin_give_item(int(m.group(1)), int(m.group(2)), m.group(3).strip())
        _send(vk, user_id, result["message"]); return True

    m = re.match(r"^админ\s+set\s+(\d+)\s+([a-z_]+)\s+(-?\d+)$", text)
    if m:
        result = database.admin_set_user_field(int(m.group(1)), m.group(2), int(m.group(3)))
        _send(vk, user_id, result["message"]); return True

    m = re.match(r"^админ\s+лоты(?:\s+(active|sold|cancelled|expired|all))?$", text)
    if m:
        status = m.group(1) or "active"
        rows = database.admin_get_market_listings(status=status, limit=30)
        if not rows:
            _send(vk, user_id, f"Лотов со статусом '{status}' нет."); return True
        lines = [f"🧾 ЛОТЫ ({status})\n"]
        for r in rows:
            lines.append(f"#{r['id']} | {r['item_name']} x{r['quantity']} | {r['price_per_item']} руб | {r['status']} | seller={r['seller_vk_id']}")
        _send(vk, user_id, "\n".join(lines)); return True

    m = re.match(r"^админ\s+снять\s+лот\s+(\d+)$", text)
    if m:
        result = database.admin_cancel_market_listing(int(m.group(1)))
        _send(vk, user_id, result["message"]); return True

    m = re.match(r"^админ\s+квесты\s+(\d+)$", text)
    if m:
        target = int(m.group(1))
        user = database.get_admin_user(target)
        if not user:
            _send(vk, user_id, "Пользователь не найден."); return True
        quests_info = database.get_daily_quests_for_user(target)
        if not quests_info:
            _send(vk, user_id, f"📋 Квесты {user['name']}:\n\nЕжедневных квестов нет."); return True
        lines = [f"📋 КВЕСТЫ: {user['name']} (vk:{target})\n"]
        if quests_info.get("quest_date"):
            lines.append(f"Дата: {quests_info['quest_date']}")
        if quests_info.get("updated_at"):
            lines.append(f"Обновлено: {quests_info['updated_at']}")
        lines.append(f"Стрик: {quests_info['streak']} дней")
        lines.append(f"Claimed: {'да' if quests_info['claimed'] else 'нет'}\n")
        for i, q in enumerate(quests_info.get("quests", []), 1):
            qid = q["id"]
            qtype = q.get("type", "?")
            progress = quests_info.get("progress", {}).get(qid, 0)
            target_val = q.get("target", "?")
            reward = q.get("reward_xp", 0)
            lines.append(f"{i}. [{qtype}] {progress}/{target_val} → XP:{reward}")
        _send(vk, user_id, "\n".join(lines)); return True

    m = re.match(r"^админ\s+рандом\s+(\d+)$", text)
    if m:
        target = int(m.group(1))
        from state_manager import has_pending_event, clear_pending_event, set_pending_event
        from random_events import get_random_event, format_event_message
        from handlers.keyboards import create_random_event_keyboard
        if has_pending_event(target): clear_pending_event(target)
        event = get_random_event(user_id=target)
        if not event:
            _send(vk, user_id, "❌ Рандомное событие не сгенерировалось."); return True
        set_pending_event(target, event)
        try:
            vk.messages.send(user_id=target, message=f"🎲 **АДМИНСКИЙ ИВЕНТ**\n\n{format_event_message(event)}", keyboard=create_random_event_keyboard(event).get_keyboard(), random_id=0)
            _send(vk, user_id, f"✅ Ивент отправлен vk:{target} | Тип: {event.get('type', '?')}")
        except Exception as e:
            _send(vk, user_id, f"❌ Ошибка: {e}")
        return True

    m = re.match(r"^админ\s+кулдаун\s+(\d+)\s+(снять|инфо)$", text)
    if m:
        target = int(m.group(1))
        action = m.group(2)
        user = database.get_admin_user(target)
        if not user:
            _send(vk, user_id, "Пользователь не найден."); return True
        from handlers.location import get_event_spawn_state
        now_ts = int(time.time())
        last_time = database.get_user_flag(target, "last_random_event_time", 0)
        if action == "инфо":
            if last_time == 0:
                _send(vk, user_id, f"⏰ Кулдаун {user['name']}:\n\nСобытий ещё не было.")
            else:
                state = get_event_spawn_state(last_time, now=now_ts)
                elapsed = state["elapsed"]
                mins = elapsed // 60
                if not state["ready"]:
                    _send(
                        vk,
                        user_id,
                        f"⏰ Кулдаун {user['name']}:\n\n"
                        f"Последнее событие: {mins} мин назад\n"
                        f"⏳ Осталось: {state['cooldown_remaining'] // 60} мин",
                    )
                else:
                    _send(
                        vk,
                        user_id,
                        f"⏰ Кулдаун {user['name']}:\n\n"
                        f"Последнее событие: {mins} мин назад\n"
                        f"✅ Кулдаун прошёл\n"
                        f"🎲 Шанс: {state['chance']:.1f}%",
                    )
            return True
        if action == "снять":
            database.set_user_flag(target, "last_random_event_time", 0)
            _send(vk, user_id, f"✅ Кулдаун сброшен для {user['name']}.")
            return True

    m = re.match(r"^админ\s+инвентарь\s+(\d+)$", text)
    if m:
        target = int(m.group(1))
        user = database.get_admin_user(target)
        if not user:
            _send(vk, user_id, "Пользователь не найден."); return True
        inventory = database.get_user_inventory(target)
        if not inventory:
            _send(vk, user_id, f"🎒 Инвентарь {user['name']}:\n\nПусто."); return True
        lines = [f"🎒 ИНВЕНТАРЬ: {user['name']} (vk:{target})\n"]
        for item in inventory:
            lines.append(f"• {item['name']} x{item['quantity']} (цена:{item['price']} урон:{item.get('attack', 0)} защ:{item.get('defense', 0)})")
        _send(vk, user_id, "\n".join(lines)); return True

    m = re.match(r"^админ\s+локация\s+(\d+)\s+(.+)$", text)
    if m:
        target = int(m.group(1))
        new_location = m.group(2).strip()
        from constants import LocationType
        valid_locations = {loc.value for loc in LocationType}
        if new_location not in valid_locations:
            _send(vk, user_id, f"❌ Неверная локация. Доступные: {', '.join(sorted(valid_locations))}"); return True
        database.update_user_location(target, new_location)
        user = database.get_admin_user(target)
        _send(vk, user_id, f"✅ {user['name']} → '{new_location}'."); return True

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

    # Fallback — главное меню
    _show_main_menu(vk, user_id)
    return True
