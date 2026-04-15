"""
Обработчики ежедневных заданий
"""
import database
from daily_quests import format_daily_quests_header
from handlers.keyboards import create_daily_quests_keyboard


def handle_daily_quests_command(player, vk, user_id: int, text: str) -> bool:
    """Обработка команд daily quests"""
    from state_manager import try_edit_or_send
    text_lower = text.strip().lower()

    if text_lower not in (
        "задания", "ежедневные задания", "квесты", "daily", "/daily",
        "задания показать", "квесты показать", "мои задания",
    ):
        return False

    # Получаем или генерируем задания
    quests, progress, streak = database.reset_daily_quests_if_needed(user_id)

    msg = format_daily_quests_header(quests, progress, streak)

    try_edit_or_send(
        vk, user_id,
        message=msg,
        keyboard=create_daily_quests_keyboard(),
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
            keyboard=create_daily_quests_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    if result.get("error") == "already_claimed":
        vk.messages.send(
            user_id=user_id,
            message="🎁 Ты уже забрал награду сегодня. Приходи завтра!",
            keyboard=create_daily_quests_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    if result.get("error") == "not_found":
        vk.messages.send(
            user_id=user_id,
            message="⚠️ Сегодняшние задания не найдены. Напиши 'мои задания' для генерации.",
            keyboard=create_daily_quests_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    if result.get("error") == "not_all_complete":
        vk.messages.send(
            user_id=user_id,
            message="⬜ Ты ещё не выполнил все задания. Выполни все 3, чтобы забрать награду!",
            keyboard=create_daily_quests_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    if result.get("error") == "exception":
        vk.messages.send(
            user_id=user_id,
            message="⚠️ Ошибка при получении награды. Попробуй позже или напиши админу.",
            keyboard=create_daily_quests_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    # Успешная награда
    msg = "🎉 НАГРАДА ПОЛУЧЕНА!\n\n"
    msg += f"⭐ Опыт: +{result['xp']:,} XP\n"
    msg += f"💰 Деньги: +{result['money']:,} руб.\n"

    if result.get("bonus_items"):
        msg += "\n🎁 Бонусные предметы:\n"
        for item_name, qty in result["bonus_items"]:
            msg += f"   • {item_name} x{qty}\n"

    msg += f"\n📊 Всего: {result['new_money']:,} руб., {result['new_xp']:,} XP\n"
    msg += f"🔥 Серия: {result['new_streak']} дн."

    vk.messages.send(
        user_id=user_id,
        message=msg,
        keyboard=create_daily_quests_keyboard().get_keyboard(),
        random_id=0,
    )
    return True


def track_quest_kill(user_id: int, location: str = None):
    """Отслеживать убийства для заданий"""
    database.track_quest_progress(user_id, "kill", location)


def track_quest_explore(user_id: int, location: str = None):
    """Отслеживать исследование для заданий"""
    database.track_quest_progress(user_id, "explore", location)


def track_quest_artifact(user_id: int):
    """Отслеживать сбор артефактов для заданий"""
    database.track_quest_progress(user_id, "collect_artifact")


def track_quest_shells(user_id: int, count: int = 1):
    """Отслеживать сбор гильз для заданий"""
    database.track_quest_progress(user_id, "collect_shells", increment=count)


def track_quest_visit(user_id: int, location: str):
    """Отслеживать посещение локаций для заданий"""
    database.track_quest_progress(user_id, "visit_location", location)


def track_quest_market_list(user_id: int):
    """Отслеживать выставление лота для заданий"""
    database.track_quest_progress(user_id, "market_list")


def track_quest_market_buy(user_id: int):
    """Отслеживать покупку лота для заданий"""
    database.track_quest_progress(user_id, "market_buy")


def track_quest_talk_npc(user_id: int):
    """Отслеживать разговор с NPC для заданий"""
    database.track_quest_progress(user_id, "talk_npc")


def track_quest_change_class(user_id: int):
    """Отслеживать смену класса для заданий"""
    database.track_quest_progress(user_id, "change_class")


def track_quest_shop_buy(user_id: int):
    """Отслеживать покупку у NPC-магазинов для заданий"""
    database.track_quest_progress(user_id, "shop_buy")


def track_quest_shop_sell(user_id: int):
    """Отслеживать продажу NPC-магазинам для заданий"""
    database.track_quest_progress(user_id, "shop_sell")
