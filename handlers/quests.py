"""
Обработчики ежедневных заданий
"""
from __future__ import annotations

from infra import database
from game.daily_quests import format_daily_quests_header
from handlers.keyboards import create_quests_keyboard


STORY_QUEST_ACTIVE = 1
STORY_QUEST_COMPLETED = 2
QUESTS_TOTAL_PAGES = 3

STORY_QUESTS = {
    "forester_marks": {
        "title": "Метки Лесника",
        "giver": "Лесник",
        "location": "Заимка лесника",
        "summary": "Лесник проверяет, умеешь ли ты читать лес, прежде чем открыть путь в охотничьи угодья.",
        "objectives": [
            "Ответить на проверку следа у Лесника.",
            "Выбрать правильный заход по ветру.",
            "Разобрать приманку на поляне.",
        ],
        "reward": "Маршрут в Охотничьи угодья, доступ к AFK-охоте и скупке редких трофеев.",
    },
}


def _quest_state_flag(quest_id: str) -> str:
    return f"story_quest:{quest_id}:state"


def accept_story_quest(user_id: int, quest_id: str):
    """Записать сюжетный квест в журнал, если он ещё не завершён."""
    if quest_id not in STORY_QUESTS:
        return
    current = int(database.get_user_flag(user_id, _quest_state_flag(quest_id), 0) or 0)
    if current < STORY_QUEST_COMPLETED:
        database.set_user_flag(user_id, _quest_state_flag(quest_id), STORY_QUEST_ACTIVE)


def complete_story_quest(user_id: int, quest_id: str):
    """Пометить сюжетный квест завершённым."""
    if quest_id not in STORY_QUESTS:
        return
    database.set_user_flag(user_id, _quest_state_flag(quest_id), STORY_QUEST_COMPLETED)


def _get_story_quest_rows(user_id: int, state: int) -> list[tuple[str, dict]]:
    rows = []
    for quest_id, quest in STORY_QUESTS.items():
        current = int(database.get_user_flag(user_id, _quest_state_flag(quest_id), 0) or 0)
        if current == state:
            rows.append((quest_id, quest))
    return rows


def _format_story_quest(quest: dict, *, completed: bool) -> str:
    status = "✅" if completed else "⬜"
    lines = [
        f"{status} {quest['title']}",
        f"   Кто дал: {quest['giver']}",
        f"   Где: {quest['location']}",
        f"   Кратко: {quest['summary']}",
        "   Цели:",
    ]
    lines.extend(f"   • {objective}" for objective in quest.get("objectives", []))
    lines.append(f"   Награда: {quest['reward']}")
    return "\n".join(lines)


def _format_story_quests_page(user_id: int, *, completed: bool) -> str:
    state = STORY_QUEST_COMPLETED if completed else STORY_QUEST_ACTIVE
    rows = _get_story_quest_rows(user_id, state)
    title = "✅ ЗАВЕРШЁННЫЕ ЗАДАНИЯ" if completed else "📌 АКТИВНЫЕ ЗАДАНИЯ"
    msg = f"{title}\n━━━━━━━━━━━━━━━━━━━━━━━\n"
    if not rows:
        msg += "Пока пусто.\n"
        if not completed:
            msg += "Новые задания появятся здесь после принятия у NPC или в событиях."
        return msg
    msg += "\n\n".join(_format_story_quest(quest, completed=completed) for _, quest in rows)
    return msg


def _send_daily_progress_notifications(vk, user_id: int, progress_result: dict | None):
    """Отправить уведомления о прогрессе/выполнении ежедневных заданий."""
    if not vk or not progress_result:
        return

    completed_now = progress_result.get("completed_now") or []
    for quest in completed_now:
        msg = (
            f"✅ Дейлик выполнен: {quest.get('text', quest.get('id', ''))}\n"
            f"Прогресс: {quest.get('after', 0)}/{quest.get('target', 1)}"
        )
        vk.messages.send(user_id=user_id, message=msg, random_id=0)

    if progress_result.get("all_completed_now"):
        vk.messages.send(
            user_id=user_id,
            message="🎁 Все ежедневные задания выполнены!\nМожно забрать награду: напиши 'забрать награду'.",
            random_id=0,
        )


def handle_daily_quests_command(player, vk, user_id: int, text: str) -> bool:
    """Обработка вкладки заданий."""
    from infra.state_manager import try_edit_or_send
    text_lower = text.strip().lower()

    aliases = {
        "задания": 0,
        "квесты": 0,
        "мои задания": 0,
        "задания показать": 0,
        "квесты показать": 0,
        "активные задания": 0,
        "задания активные": 0,
        "задания далее": 1,
        "следующая страница заданий": 1,
        "завершенные задания": 1,
        "завершённые задания": 1,
        "задания назад": 2,
        "ежедневные задания": 2,
        "дейлики": 2,
        "daily": 2,
        "/daily": 2,
    }
    if text_lower not in aliases:
        return False

    page = aliases[text_lower]
    if page == 2:
        quests, progress, streak = database.reset_daily_quests_if_needed(user_id)
        msg = format_daily_quests_header(quests, progress, streak, user_id=user_id)
    elif page == 1:
        msg = _format_story_quests_page(user_id, completed=True)
    else:
        msg = _format_story_quests_page(user_id, completed=False)

    try_edit_or_send(
        vk, user_id,
        message=msg,
        keyboard=create_quests_keyboard(page, QUESTS_TOTAL_PAGES),
    )
    return True


def handle_claim_rewards(player, vk, user_id: int, text: str) -> bool:
    """Забрать награду за ежедневные задания"""
    text_lower = text.strip().lower()
    if text_lower not in (
        "задания забрать", "забрать награду", "забрать", "claim",
        "получить награду", "забрать квест",
    ):
        return False

    result = database.claim_daily_rewards(user_id)
    if not result:
        vk.messages.send(
            user_id=user_id,
            message="⚠️ Задания не найдены. Напиши 'задания' чтобы получить новые.",
            keyboard=create_quests_keyboard(2, QUESTS_TOTAL_PAGES).get_keyboard(),
            random_id=0,
        )
        return True

    if result.get("error") == "already_claimed":
        vk.messages.send(
            user_id=user_id,
            message="🎁 Ты уже забрал награду сегодня. Приходи завтра!",
            keyboard=create_quests_keyboard(2, QUESTS_TOTAL_PAGES).get_keyboard(),
            random_id=0,
        )
        return True

    if result.get("error") == "not_found":
        vk.messages.send(
            user_id=user_id,
            message="⚠️ Сегодняшние задания не найдены. Напиши 'мои задания' для генерации.",
            keyboard=create_quests_keyboard(2, QUESTS_TOTAL_PAGES).get_keyboard(),
            random_id=0,
        )
        return True

    if result.get("error") == "not_all_complete":
        vk.messages.send(
            user_id=user_id,
            message="⬜ Ты ещё не выполнил все задания. Выполни все 3, чтобы забрать награду!",
            keyboard=create_quests_keyboard(2, QUESTS_TOTAL_PAGES).get_keyboard(),
            random_id=0,
        )
        return True

    if result.get("error") == "exception":
        vk.messages.send(
            user_id=user_id,
            message="⚠️ Ошибка при получении награды. Попробуй позже.",
            keyboard=create_quests_keyboard(2, QUESTS_TOTAL_PAGES).get_keyboard(),
            random_id=0,
        )
        return True

    # Успешная награда
    from game.gacha.service import grant_daily_quest_shards, grant_weekly_quest_shards

    shard_reward = grant_daily_quest_shards(user_id, int(result.get("new_streak", 1) or 1))
    weekly_shard_reward = grant_weekly_quest_shards(user_id)
    msg = "🎉 НАГРАДА ПОЛУЧЕНА!\n\n"
    msg += f"⭐ Опыт: +{result['xp']:,} XP\n"
    msg += f"💰 Деньги: +{result['money']:,} руб.\n"
    if shard_reward.get("granted", 0) > 0:
        msg += f"💠 Осколки сигнала: +{shard_reward['granted']}\n"
    if weekly_shard_reward.get("granted", 0) > 0:
        msg += f"⚡ Недельная цель Резонанса: +{weekly_shard_reward['granted']} осколков\n"
    else:
        msg += (
            f"⚡ Недельная цель Резонанса: "
            f"{weekly_shard_reward.get('count', 0)}/{weekly_shard_reward.get('target', 5)}\n"
        )

    if result.get("bonus_items"):
        msg += "\n🎁 Бонусные предметы:\n"
        for item_name, qty in result["bonus_items"]:
            msg += f"   • {item_name} x{qty}\n"

    level_up = result.get("level_up")
    if level_up:
        msg += (
            "\n⭐ НОВЫЙ УРОВЕНЬ!\n"
            f"   {level_up['old_level']} → {level_up['new_level']}\n"
            "   Здоровье и энергия восстановлены.\n"
            f"   Очков характеристик: +{level_up.get('stat_points', 0)}\n"
            "   Выбор характеристики появится отдельным сообщением, когда не будет активных событий.\n"
        )
        if level_up.get("rank_cap_reached"):
            msg += "   Достигнут потолок текущего ранга. Для дальнейшего роста повысь ранг у Куратора рангов.\n"

    msg += f"\n📊 Всего: {result['new_money']:,} руб., {result['new_xp']:,} XP\n"
    msg += f"🔥 Серия: {result['new_streak']} дн."

    vk.messages.send(
        user_id=user_id,
        message=msg,
        keyboard=create_quests_keyboard(2, QUESTS_TOTAL_PAGES).get_keyboard(),
        random_id=0,
    )
    return True


def track_quest_kill(user_id: int, location: str = None, vk=None):
    """Отслеживать убийства для заданий"""
    res = database.track_quest_progress(user_id, "kill", location)
    _send_daily_progress_notifications(vk, user_id, res)


def track_quest_explore(user_id: int, location: str = None, vk=None):
    """Отслеживать исследование для заданий"""
    res = database.track_quest_progress(user_id, "explore", location)
    _send_daily_progress_notifications(vk, user_id, res)


def track_quest_artifact(user_id: int, vk=None):
    """Отслеживать сбор артефактов для заданий"""
    res = database.track_quest_progress(user_id, "collect_artifact")
    _send_daily_progress_notifications(vk, user_id, res)


def track_quest_shells(user_id: int, count: int = 1, vk=None):
    """Отслеживать сбор гильз для заданий"""
    res = database.track_quest_progress(user_id, "collect_shells", increment=count)
    _send_daily_progress_notifications(vk, user_id, res)


def track_quest_visit(user_id: int, location: str, vk=None):
    """Отслеживать посещение локаций для заданий"""
    res = database.track_quest_progress(user_id, "visit_location", location)
    _send_daily_progress_notifications(vk, user_id, res)


def track_quest_market_list(user_id: int, vk=None):
    """Отслеживать выставление лота для заданий"""
    res = database.track_quest_progress(user_id, "market_list")
    _send_daily_progress_notifications(vk, user_id, res)


def track_quest_market_buy(user_id: int, vk=None):
    """Отслеживать покупку лота для заданий"""
    res = database.track_quest_progress(user_id, "market_buy")
    _send_daily_progress_notifications(vk, user_id, res)


def track_quest_talk_npc(user_id: int, vk=None):
    """Отслеживать разговор с NPC для заданий"""
    res = database.track_quest_progress(user_id, "talk_npc")
    _send_daily_progress_notifications(vk, user_id, res)


def track_quest_change_class(user_id: int, vk=None):
    """Отслеживать смену класса для заданий"""
    res = database.track_quest_progress(user_id, "change_class")
    _send_daily_progress_notifications(vk, user_id, res)


def track_quest_shop_buy(user_id: int, vk=None):
    """Отслеживать покупку у NPC-магазинов для заданий"""
    res = database.track_quest_progress(user_id, "shop_buy")
    _send_daily_progress_notifications(vk, user_id, res)


def track_quest_shop_sell(user_id: int, vk=None):
    """Отслеживать продажу NPC-магазинам для заданий"""
    res = database.track_quest_progress(user_id, "shop_sell")
    _send_daily_progress_notifications(vk, user_id, res)
