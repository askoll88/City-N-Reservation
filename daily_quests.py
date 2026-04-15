"""
Система ежедневных заданий (Daily Quests)
Лор S.T.A.L.K.E.R. - Зона каждый день преподносит новое.

Задания ротируются в полночь (по UTC).
Игрок получает 3 задания в день. Награда растёт с серией дней (streak).
"""
import random
from datetime import datetime, timezone
from typing import Optional


# === Пул заданий ===
QUEST_POOL = [
    {
        "id": "kill_military_road",
        "text": "Зачисти Дорогу на военную часть - убей 3 врагов",
        "type": "kill",
        "location": "дорога_военная_часть",
        "target": 3,
        "reward_xp": 150,
        "reward_money": 200,
        "flavor": "Военные не дадут пройти просто так. Разберись с ними."
    },
    {
        "id": "kill_nii_road",
        "text": "Зачисти Дорогу на НИИ - убей 3 врагов",
        "type": "kill",
        "location": "дорога_нии",
        "target": 3,
        "reward_xp": 150,
        "reward_money": 200,
        "flavor": "Охрана НИИ не дремлет. Покажи им, кто тут хозяин."
    },
    {
        "id": "kill_infected_forest",
        "text": "Зачисти Заражённый лес - убей 4 мутантов",
        "type": "kill",
        "location": "дорога_зараженный_лес",
        "target": 4,
        "reward_xp": 200,
        "reward_money": 250,
        "flavor": "Мутанты облюбовали лес. Время устроить охоту."
    },
    {
        "id": "kill_any_5",
        "text": "Убей 5 врагов в Зоне (любых)",
        "type": "kill_any",
        "target": 5,
        "reward_xp": 180,
        "reward_money": 220,
        "flavor": "Зона опасна, но ты опаснее."
    },
    {
        "id": "kill_any_10",
        "text": "Убей 10 врагов в Зоне (любых)",
        "type": "kill_any",
        "target": 10,
        "reward_xp": 400,
        "reward_money": 500,
        "flavor": "Серьёзная зачистка. Сталкеры оценят."
    },
    {
        "id": "collect_artifact_1",
        "text": "Найди 1 артефакт в аномалии",
        "type": "collect_artifact",
        "target": 1,
        "reward_xp": 100,
        "reward_money": 150,
        "flavor": "Артефакт - валюта Зоны. Найди хотя бы один."
    },
    {
        "id": "collect_artifact_3",
        "text": "Найди 3 артефакта в аномалиях",
        "type": "collect_artifact",
        "target": 3,
        "reward_xp": 350,
        "reward_money": 400,
        "flavor": "Три артефакта - хороший улов для сталкера."
    },
    {
        "id": "explore_2",
        "text": "Исследуй 2 локации в Зоне",
        "type": "explore",
        "target": 2,
        "reward_xp": 120,
        "reward_money": 100,
        "flavor": "Разведка - мать выживания. Исследуй Зону."
    },
    {
        "id": "explore_5",
        "text": "Исследуй 5 локаций в Зоне",
        "type": "explore",
        "target": 5,
        "reward_xp": 300,
        "reward_money": 250,
        "flavor": "Пять вылазок - ты настоящий разведчик."
    },
    {
        "id": "shells_10",
        "text": "Собери 10 гильз",
        "type": "collect_shells",
        "target": 10,
        "reward_xp": 80,
        "reward_money": 50,
        "flavor": "Гильзы нужны для добычи артефактов. Не выбрасывай их."
    },
    {
        "id": "shells_30",
        "text": "Собери 30 гильз",
        "type": "collect_shells",
        "target": 30,
        "reward_xp": 200,
        "reward_money": 150,
        "flavor": "Целая куча гильз. Учёные будут довольны."
    },
    {
        "id": "visit_hospital",
        "text": "Полечись в больнице",
        "type": "visit_location",
        "location": "больница",
        "target": 1,
        "reward_xp": 50,
        "reward_money": 0,
        "flavor": "Бережёного Зона бережёт. Зайди к врачу."
    },
    {
        "id": "visit_shelter",
        "text": "Посети убежище",
        "type": "visit_location",
        "location": "убежище",
        "target": 1,
        "reward_xp": 50,
        "reward_money": 0,
        "flavor": "Сталкеру нужен отдых. Загляни в убежище."
    },
    {
        "id": "market_sell",
        "text": "Выставь 1 лот на P2P рынке",
        "type": "market_list",
        "target": 1,
        "reward_xp": 100,
        "reward_money": 100,
        "flavor": "Торговля - двигатель Зоны. Продай что-нибудь на рынке."
    },
    {
        "id": "market_buy",
        "text": "Купи 1 лот на P2P рынке",
        "type": "market_buy",
        "target": 1,
        "reward_xp": 100,
        "reward_money": 100,
        "flavor": "Поддержи сталкерскую экономику."
    },
    {
        "id": "shop_buy_3",
        "text": "Купи 3 предмета у NPC-торговцев",
        "type": "shop_buy",
        "target": 3,
        "reward_xp": 140,
        "reward_money": 180,
        "flavor": "Запасись снаряжением перед вылазкой."
    },
    {
        "id": "shop_sell_5",
        "text": "Продай 5 предметов NPC-торговцам",
        "type": "shop_sell",
        "target": 5,
        "reward_xp": 170,
        "reward_money": 220,
        "flavor": "Разгрузи рюкзак и подзаработай."
    },
    {
        "id": "talk_npc",
        "text": "Поговори с любым NPC",
        "type": "talk_npc",
        "target": 1,
        "reward_xp": 40,
        "reward_money": 30,
        "flavor": "Разговоры - источник информации. Поговори с кем-нибудь."
    },
]


STREAK_BONUSES = {
    1: {"multiplier": 1.0,  "title": "Первый день",            "bonus_item": None},
    2: {"multiplier": 1.2,  "title": "Два дня подряд",         "bonus_item": ("Бинт", 2)},
    3: {"multiplier": 1.5,  "title": "Три дня подряд",         "bonus_item": ("Аптечка", 1)},
    5: {"multiplier": 2.0,  "title": "Пять дней подряд",       "bonus_item": ("Антидот", 1)},
    7: {"multiplier": 2.5,  "title": "Неделя подряд!",         "bonus_item": ("Детектор аномалий", 1)},
    14: {"multiplier": 3.0, "title": "Две недели подряд!",     "bonus_item": ("Бронежилет", 1)},
    30: {"multiplier": 5.0, "title": "Легенда Зоны (30 дней)", "bonus_item": ("Комбинезон сталкера", 1)},
}


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_best_streak_bonus(streak: int) -> dict:
    best = STREAK_BONUSES[1]
    for threshold, bonus in sorted(STREAK_BONUSES.items()):
        if streak >= threshold:
            best = bonus
        else:
            break
    return best


def generate_daily_quests(seed: str = None) -> list:
    if seed is None:
        seed = _today_key()

    rng = random.Random(seed)
    quest_types = set()
    selected = []
    pool_copy = list(QUEST_POOL)
    rng.shuffle(pool_copy)

    for quest in pool_copy:
        if len(selected) >= 3:
            break
        qtype = quest["type"]
        if qtype not in quest_types or len(quest_types) >= 3:
            selected.append(quest)
            quest_types.add(qtype)

    if len(selected) < 3:
        for quest in pool_copy:
            if quest not in selected:
                selected.append(quest)
                if len(selected) >= 3:
                    break

    return selected[:3]


def calculate_quest_reward(quest: dict, streak: int):
    bonus = _get_best_streak_bonus(streak)
    mult = bonus["multiplier"]
    xp = int(quest["reward_xp"] * mult)
    money = int(quest["reward_money"] * mult)
    bonus_item = None
    if streak in STREAK_BONUSES and STREAK_BONUSES[streak].get("bonus_item"):
        bonus_item = STREAK_BONUSES[streak]["bonus_item"]
    return xp, money, bonus_item


def format_quest_display(quest: dict, progress: int, streak: int) -> str:
    target = quest["target"]
    done = min(progress, target)
    pct = int(done / target * 100)
    completed = "✅" if done >= target else "⬜"
    streak_text = f" | 🔥 {streak} дн." if streak > 0 else ""
    bar_len = done * 10 // target
    bar = "█" * bar_len + "░" * (10 - bar_len)

    lines = [
        f"{completed} {quest['text']}",
        f"   [{bar}] {done}/{target} ({pct}%){streak_text}",
        f"   🎁 Награда: {quest['reward_xp']} XP, {quest['reward_money']} руб.",
    ]
    if quest.get("flavor"):
        lines.append(f"   💬 {quest['flavor']}")
    return "\n".join(lines)


def _get_streak_title(streak: int) -> str:
    title = "Новичок"
    for threshold, bonus in sorted(STREAK_BONUSES.items()):
        if streak >= threshold:
            title = bonus["title"]
    return title


def format_daily_quests_header(quests: list, progresses: dict, streak: int) -> str:
    today = _today_key()
    title = _get_streak_title(streak)

    msg = "📋 ЕЖЕДНЕВНЫЕ ЗАДАНИЯ\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📅 {today} | 🔥 Серия: {streak} дн. | 🏅 {title}\n\n"

    for i, quest in enumerate(quests, 1):
        qid = quest["id"]
        progress = progresses.get(qid, 0)
        msg += f"{i}. {format_quest_display(quest, progress, streak)}\n\n"

    all_done = all(progresses.get(q["id"], 0) >= q["target"] for q in quests)
    if all_done:
        msg += "🎉 ВСЕ ЗАДАНИЯ ВЫПОЛНЕНЫ! Забери награду командой задания забрать\n"
    else:
        remaining = sum(1 for q in quests if progresses.get(q["id"], 0) < q["target"])
        msg += f"Осталось заданий: {remaining} из 3\n"
        msg += "Выполни все 3, чтобы получить бонус серии!\n"

    return msg
