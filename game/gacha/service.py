"""Business logic for Resonance Zone pulls."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from infra import database

from .banners import (
    BANNERS,
    BANNER_CYCLE_START_SETTING,
    BANNER_DURATION_DAYS,
    GACHA_ENABLED_SETTING,
    SIGNAL_SHARDS_FLAG,
    SINGLE_PULL_COST,
    TEN_PULL_COST,
    SR_BASE_RATE,
    SR_HARD_PITY,
    SSR_BASE_RATE,
    SSR_HARD_PITY,
    SSR_SOFT_PITY_START,
    SSR_SOFT_PITY_STEP,
    Banner,
    RewardEntry,
    get_banner,
)
from .event_items import is_gacha_event_item


DUPLICATE_SSR_PULLS = 5
DUPLICATE_SSR_SHARDS = SINGLE_PULL_COST * DUPLICATE_SSR_PULLS
SIGNAL_SHARDS_REWARD_NAME = "Осколки сигнала"
EVENT_SHARDS_DAILY_CAP = 80
COMBAT_SHARDS_DAILY_CAP = 120
RESONANCE_HISTORY_RUNTIME_KEY = "resonance_history"
RESONANCE_HISTORY_LIMIT_PER_BANNER = 50


def _today_ordinal() -> int:
    return datetime.now(timezone.utc).toordinal()


@dataclass(frozen=True)
class PullReward:
    rarity: str
    name: str
    quantity: int = 1
    kind: str = "item"
    duplicate: bool = False
    source_name: str | None = None
    featured: bool = False
    guaranteed: bool = False
    fifty_fifty_lost: bool = False
    pity_count: int = 0


def is_resonance_enabled() -> bool:
    value = database.get_game_setting(GACHA_ENABLED_SETTING, default="0")
    return str(value) == "1"


def set_resonance_enabled(enabled: bool) -> None:
    database.set_game_setting(GACHA_ENABLED_SETTING, "1" if enabled else "0")
    if enabled:
        ensure_banner_cycle()


def is_resonance_available(vk_id: int) -> bool:
    return is_resonance_enabled() and database.is_user_admin(vk_id)


def get_signal_shards(vk_id: int) -> int:
    return max(0, int(database.get_user_flag(vk_id, SIGNAL_SHARDS_FLAG, 0) or 0))


def add_signal_shards(vk_id: int, amount: int) -> int:
    safe_amount = int(amount or 0)
    current = get_signal_shards(vk_id)
    updated = max(0, current + safe_amount)
    database.set_user_flag(vk_id, SIGNAL_SHARDS_FLAG, updated)
    return updated


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def ensure_banner_cycle(now_ts: int | None = None) -> dict:
    """Получить текущий 20-дневный цикл баннеров и создать его при необходимости."""
    now = int(now_ts if now_ts is not None else _now_ts())
    duration = max(1, int(BANNER_DURATION_DAYS) * 24 * 60 * 60)
    stored = int(database.get_game_setting(BANNER_CYCLE_START_SETTING, default="0") or 0)
    if stored <= 0:
        stored = now
        database.set_game_setting(BANNER_CYCLE_START_SETTING, str(stored))
    if now >= stored + duration:
        passed = (now - stored) // duration
        stored = stored + passed * duration
        database.set_game_setting(BANNER_CYCLE_START_SETTING, str(stored))
    end_ts = stored + duration
    return {
        "start_ts": stored,
        "end_ts": end_ts,
        "remaining_seconds": max(0, end_ts - now),
        "duration_seconds": duration,
    }


def format_seconds_left(seconds: int) -> str:
    remaining = max(0, int(seconds or 0))
    days, rem = divmod(remaining, 24 * 60 * 60)
    hours, rem = divmod(rem, 60 * 60)
    minutes, secs = divmod(rem, 60)
    return f"{days}д {hours:02d}:{minutes:02d}:{secs:02d}"


def get_banner_time_left() -> dict:
    cycle = ensure_banner_cycle()
    return {**cycle, "formatted": format_seconds_left(cycle["remaining_seconds"])}


def add_signal_shards_capped(vk_id: int, amount: int, source: str, daily_cap: int) -> dict:
    """Начислить осколки с дневным лимитом по источнику."""
    safe_amount = max(0, int(amount or 0))
    safe_cap = max(0, int(daily_cap or 0))
    if safe_amount <= 0:
        return {"granted": 0, "balance": get_signal_shards(vk_id), "cap": safe_cap, "used": 0}

    key = str(source or "misc").strip().lower() or "misc"
    day_flag = f"resonance_{key}_shards_day"
    used_flag = f"resonance_{key}_shards_used"
    today = _today_ordinal()
    stored_day = int(database.get_user_flag(vk_id, day_flag, 0) or 0)
    used = int(database.get_user_flag(vk_id, used_flag, 0) or 0) if stored_day == today else 0

    grant = safe_amount
    if safe_cap > 0:
        grant = min(safe_amount, max(0, safe_cap - used))
    if grant <= 0:
        return {"granted": 0, "balance": get_signal_shards(vk_id), "cap": safe_cap, "used": used}

    balance = add_signal_shards(vk_id, grant)
    database.set_user_flag(vk_id, day_flag, today)
    database.set_user_flag(vk_id, used_flag, used + grant)
    return {"granted": grant, "balance": balance, "cap": safe_cap, "used": used + grant}


def grant_daily_quest_shards(vk_id: int, streak: int) -> dict:
    """Награда за полный комплект ежедневных заданий."""
    safe_streak = max(1, int(streak or 1))
    amount = 50 + min(30, safe_streak * 2)
    if safe_streak >= 7:
        amount += 20
    if safe_streak >= 14:
        amount += 20
    if safe_streak >= 30:
        amount += 30
    return {"granted": amount, "balance": add_signal_shards(vk_id, amount), "cap": 0, "used": 0}


def grant_event_shards(vk_id: int, event: dict, result: dict) -> dict:
    """Малые осколки за полезный исход случайного/сюжетного события."""
    if not result or result.get("invalid") or result.get("next_stage") is not None:
        return {"granted": 0, "balance": get_signal_shards(vk_id), "cap": EVENT_SHARDS_DAILY_CAP, "used": 0}

    message = str(result.get("message") or "").lower()
    positive_markers = (
        "+", "xp", "руб", "артефакт", "тайник", "схрон", "припас",
        "координат", "цепочка завершена", "квест завершён", "квест завершен",
    )
    if not any(marker in message for marker in positive_markers):
        return {"granted": 0, "balance": get_signal_shards(vk_id), "cap": EVENT_SHARDS_DAILY_CAP, "used": 0}

    event_type = str((event or {}).get("type") or "").lower()
    amount_by_type = {
        "reward": 8,
        "neutral": 5,
        "danger": 10,
        "story": 12,
        "multi_stage": 22,
    }
    amount = amount_by_type.get(event_type, 6)
    if "артефакт" in message:
        amount += 8
    if "тайник" in message or "схрон" in message:
        amount += 4
    if "цепочка завершена" in message or "квест заверш" in message:
        amount = max(amount, 40)

    return add_signal_shards_capped(vk_id, amount, "event", EVENT_SHARDS_DAILY_CAP)


def grant_combat_shards(vk_id: int, enemy_level: int, reward_mult: float, player_level: int = 1) -> dict:
    """Осколки за действительно сложные победы, с дневным лимитом."""
    safe_enemy_level = max(1, int(enemy_level or 1))
    safe_player_level = max(1, int(player_level or 1))
    safe_mult = max(1.0, float(reward_mult or 1.0))
    level_gap = safe_enemy_level - safe_player_level
    if safe_mult < 1.45 and safe_enemy_level < 25 and level_gap < 5:
        return {"granted": 0, "balance": get_signal_shards(vk_id), "cap": COMBAT_SHARDS_DAILY_CAP, "used": 0}

    amount = 4 + max(0, int((safe_mult - 1.0) * 12)) + max(0, level_gap // 3) + safe_enemy_level // 30
    amount = max(4, min(24, amount))
    return add_signal_shards_capped(vk_id, amount, "combat", COMBAT_SHARDS_DAILY_CAP)


def grant_dungeon_shards(vk_id: int, threat_id: str) -> dict:
    amount_by_threat = {
        "i": 8,
        "ii": 12,
        "iii": 18,
        "iv": 26,
        "v": 36,
    }
    amount = amount_by_threat.get(str(threat_id or "").strip().lower(), 8)
    return add_signal_shards_capped(vk_id, amount, "combat", COMBAT_SHARDS_DAILY_CAP)


def _flag_name(banner_id: str, suffix: str) -> str:
    return f"resonance_{banner_id}_{suffix}"


def _get_banner_state(vk_id: int, banner_id: str) -> dict:
    return {
        "pity_ssr": max(0, int(database.get_user_flag(vk_id, _flag_name(banner_id, "pity_ssr"), 0) or 0)),
        "pity_sr": max(0, int(database.get_user_flag(vk_id, _flag_name(banner_id, "pity_sr"), 0) or 0)),
        "featured_guaranteed": int(database.get_user_flag(vk_id, _flag_name(banner_id, "featured_guaranteed"), 0) or 0) == 1,
    }


def _save_banner_state(vk_id: int, banner_id: str, state: dict) -> None:
    database.set_user_flag(vk_id, _flag_name(banner_id, "pity_ssr"), int(state.get("pity_ssr", 0) or 0))
    database.set_user_flag(vk_id, _flag_name(banner_id, "pity_sr"), int(state.get("pity_sr", 0) or 0))
    database.set_user_flag(
        vk_id,
        _flag_name(banner_id, "featured_guaranteed"),
        1 if state.get("featured_guaranteed") else 0,
    )


def get_banner_state(vk_id: int, banner_id: str) -> dict:
    banner = get_banner(banner_id)
    if not banner:
        raise ValueError("unknown banner")
    return _get_banner_state(vk_id, banner.id)


def _has_item(vk_id: int, item_name: str) -> bool:
    try:
        inventory_has = any(row.get("name") == item_name for row in database.get_user_inventory(vk_id))
        storage_has = any(row.get("name") == item_name for row in database.get_user_storage(vk_id))
        user = database.get_user_by_vk(vk_id) or {}
        equipped_has = any(
            value == item_name
            for key, value in user.items()
            if str(key).startswith("equipped_")
        )
        return inventory_has or storage_has or equipped_has
    except Exception:
        return False


def _grant_item_to_storage(vk_id: int, item_name: str, quantity: int = 1) -> bool:
    return bool(database.add_item_to_storage(vk_id, item_name, quantity))


def _grant_reward(vk_id: int, reward: PullReward) -> PullReward:
    if reward.kind == "shells":
        ok, _ = database.add_shells(vk_id, reward.quantity)
        if ok:
            return reward
        fallback = PullReward(reward.rarity, "Ржавый болт", max(1, reward.quantity // 3), kind="item")
        _grant_item_to_storage(vk_id, fallback.name, fallback.quantity)
        return fallback

    if reward.rarity == "SSR" and is_gacha_event_item(reward.name) and _has_item(vk_id, reward.name):
        add_signal_shards(vk_id, DUPLICATE_SSR_SHARDS)
        return replace(
            reward,
            name=SIGNAL_SHARDS_REWARD_NAME,
            quantity=DUPLICATE_SSR_SHARDS,
            kind="currency",
            duplicate=True,
            source_name=reward.name,
        )

    _grant_item_to_storage(vk_id, reward.name, reward.quantity)
    return reward


def _quantity(entry: RewardEntry) -> int:
    if entry.max_qty <= entry.min_qty:
        return max(1, entry.min_qty)
    return random.randint(entry.min_qty, entry.max_qty)


def _roll_entry(entry: RewardEntry, rarity: str) -> PullReward:
    return PullReward(rarity=rarity, name=entry.name, quantity=_quantity(entry), kind=entry.kind)


def _roll_ssr(banner: Banner, state: dict) -> PullReward:
    pity_count = max(1, int(state.get("pity_ssr", 1) or 1))
    if state.get("featured_guaranteed"):
        item_name = random.choice(banner.featured_ssr)
        featured = True
        guaranteed = True
        fifty_fifty_lost = False
        state["featured_guaranteed"] = False
    elif random.random() < 0.5:
        item_name = random.choice(banner.featured_ssr)
        featured = True
        guaranteed = False
        fifty_fifty_lost = False
    else:
        item_name = random.choice(banner.off_ssr or banner.featured_ssr)
        featured = item_name in banner.featured_ssr
        guaranteed = False
        fifty_fifty_lost = True
        state["featured_guaranteed"] = True
    state["pity_ssr"] = 0
    state["pity_sr"] = 0
    return PullReward(
        "SSR",
        item_name,
        featured=featured,
        guaranteed=guaranteed,
        fifty_fifty_lost=fifty_fifty_lost,
        pity_count=pity_count,
    )


def _roll_sr(banner: Banner, state: dict) -> PullReward:
    state["pity_sr"] = 0
    return _roll_entry(random.choice(banner.sr_pool), "SR")


def _roll_r(banner: Banner) -> PullReward:
    return _roll_entry(random.choice(banner.r_pool), "R")


def _current_ssr_rate(pity_ssr: int) -> float:
    if pity_ssr >= SSR_HARD_PITY:
        return 100.0
    if pity_ssr <= SSR_SOFT_PITY_START:
        return SSR_BASE_RATE
    return min(100.0, SSR_BASE_RATE + (pity_ssr - SSR_SOFT_PITY_START) * SSR_SOFT_PITY_STEP)


def _roll_one(banner: Banner, state: dict) -> PullReward:
    state["pity_ssr"] += 1
    state["pity_sr"] += 1

    if random.random() * 100 < _current_ssr_rate(state["pity_ssr"]):
        return _roll_ssr(banner, state)
    if state["pity_sr"] >= SR_HARD_PITY or random.random() * 100 < SR_BASE_RATE:
        return _roll_sr(banner, state)
    return _roll_r(banner)


def perform_pulls(vk_id: int, banner_id: str, count: int) -> dict:
    banner = get_banner(banner_id)
    if not banner:
        return {"success": False, "message": "Неизвестный баннер Резонанса."}
    if count not in {1, 10}:
        return {"success": False, "message": "Можно сделать только 1 или 10 откликов."}
    if not is_resonance_enabled():
        return {"success": False, "message": "Резонанс Зоны сейчас отключён."}
    if not database.is_user_admin(vk_id):
        return {"success": False, "message": "Резонанс Зоны пока не отвечает. Вернись позже."}

    cost = TEN_PULL_COST if count == 10 else SINGLE_PULL_COST
    current_shards = get_signal_shards(vk_id)
    if current_shards < cost:
        return {
            "success": False,
            "message": f"Не хватает осколков сигнала: нужно {cost}, у тебя {current_shards}.",
        }

    database.set_user_flag(vk_id, SIGNAL_SHARDS_FLAG, current_shards - cost)
    state = _get_banner_state(vk_id, banner.id)
    raw_rewards = [_roll_one(banner, state) for _ in range(count)]
    rewards = [_grant_reward(vk_id, reward) for reward in raw_rewards]
    _record_banner_stats(banner, raw_rewards)
    _save_banner_state(vk_id, banner.id, state)
    shards_left = get_signal_shards(vk_id)
    _record_pull_history(vk_id, banner, count, cost, rewards, shards_left)

    return {
        "success": True,
        "banner": banner,
        "count": count,
        "cost": cost,
        "shards_left": shards_left,
        "rewards": rewards,
        "state": state,
    }


def get_banners() -> tuple[Banner, ...]:
    return tuple(BANNERS.values())


def _load_pull_history(vk_id: int) -> dict:
    data = database.get_runtime_state(vk_id, RESONANCE_HISTORY_RUNTIME_KEY) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _save_pull_history(vk_id: int, data: dict) -> None:
    database.set_runtime_state(vk_id, RESONANCE_HISTORY_RUNTIME_KEY, data or {})


def _record_pull_history(
    vk_id: int,
    banner: Banner,
    count: int,
    cost: int,
    rewards: list[PullReward],
    shards_left: int,
) -> None:
    """Сохранить короткую историю откликов игрока отдельно по баннерам."""
    try:
        data = _load_pull_history(vk_id)
        rows = list(data.get(banner.id) or [])
        best_rarity = "SSR" if any(r.rarity == "SSR" for r in rewards) else "SR" if any(r.rarity == "SR" for r in rewards) else "R"
        rows.insert(0, {
            "ts": _now_ts(),
            "banner_id": banner.id,
            "banner_name": banner.name,
            "count": int(count),
            "cost": int(cost),
            "shards_left": int(shards_left),
            "best_rarity": best_rarity,
            "rewards": [
                {
                    "rarity": reward.rarity,
                    "name": reward.name,
                    "quantity": int(reward.quantity),
                    "duplicate": bool(reward.duplicate),
                    "source_name": reward.source_name,
                }
                for reward in rewards
            ],
        })
        data[banner.id] = rows[:RESONANCE_HISTORY_LIMIT_PER_BANNER]
        _save_pull_history(vk_id, data)
    except Exception:
        # История не должна ломать выдачу награды.
        return


def get_pull_history(vk_id: int, banner_id: str, page: int = 0, page_size: int = 5) -> dict:
    banner = get_banner(banner_id)
    if not banner:
        return {"banner": None, "items": [], "page": 0, "total_pages": 1, "total": 0}
    data = _load_pull_history(vk_id)
    rows = list(data.get(banner.id) or [])
    safe_size = max(1, int(page_size or 5))
    total_pages = max(1, (len(rows) + safe_size - 1) // safe_size)
    safe_page = max(0, min(total_pages - 1, int(page or 0)))
    start = safe_page * safe_size
    return {
        "banner": banner,
        "items": rows[start:start + safe_size],
        "page": safe_page,
        "total_pages": total_pages,
        "total": len(rows),
    }


def _stats_key(cycle_start_ts: int, banner_id: str) -> str:
    return f"resonance_banner_stats_{cycle_start_ts}_{banner_id}"


def _load_stats(cycle_start_ts: int, banner_id: str) -> dict:
    raw = database.get_game_setting(_stats_key(cycle_start_ts, banner_id), default="{}") or "{}"
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    defaults = {
        "pulls": 0,
        "ssr_total": 0,
        "rateup_ssr": 0,
        "fifty_fifty_losses": 0,
        "guaranteed_rateup": 0,
        "pity_sum": 0,
        "pity_count": 0,
    }
    defaults.update({key: int(value or 0) for key, value in data.items() if key in defaults})
    return defaults


def _save_stats(cycle_start_ts: int, banner_id: str, stats: dict) -> None:
    database.set_game_setting(_stats_key(cycle_start_ts, banner_id), json.dumps(stats, ensure_ascii=False, sort_keys=True))


def _record_banner_stats(banner: Banner, rewards: list[PullReward]) -> None:
    cycle = ensure_banner_cycle()
    stats = _load_stats(cycle["start_ts"], banner.id)
    stats["pulls"] += len(rewards)
    for reward in rewards:
        if reward.rarity != "SSR":
            continue
        stats["ssr_total"] += 1
        if reward.featured:
            stats["rateup_ssr"] += 1
        if reward.guaranteed:
            stats["guaranteed_rateup"] += 1
        if reward.fifty_fifty_lost:
            stats["fifty_fifty_losses"] += 1
        if reward.pity_count > 0:
            stats["pity_sum"] += int(reward.pity_count)
            stats["pity_count"] += 1
    _save_stats(cycle["start_ts"], banner.id, stats)


def get_current_banner_stats() -> dict:
    """Обезличенная агрегированная статистика текущего цикла баннеров."""
    cycle = get_banner_time_left()
    banners = []
    total = {
        "pulls": 0,
        "ssr_total": 0,
        "rateup_ssr": 0,
        "fifty_fifty_losses": 0,
        "guaranteed_rateup": 0,
        "pity_sum": 0,
        "pity_count": 0,
    }
    for banner in get_banners():
        stats = _load_stats(cycle["start_ts"], banner.id)
        average_pity = stats["pity_sum"] / stats["pity_count"] if stats["pity_count"] else 0.0
        banners.append({"banner": banner, "stats": stats, "average_pity": average_pity})
        for key in total:
            total[key] += stats.get(key, 0)
    total_average = total["pity_sum"] / total["pity_count"] if total["pity_count"] else 0.0
    return {"cycle": cycle, "banners": banners, "total": total, "total_average_pity": total_average}
