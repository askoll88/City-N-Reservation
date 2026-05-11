"""Business logic for Resonance Zone pulls."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from infra import database

from .banners import (
    BANNERS,
    BANNER_CYCLE_START_SETTING,
    BANNER_DURATION_DAYS,
    BANNER_PHASES_PER_PATCH,
    BANNER_PATCH_DURATION_DAYS,
    BANNER_ROTATION_INDEX_SETTING,
    FEATURED_SSR_CONSOLIDATED_RATE,
    GACHA_ENABLED_SETTING,
    SIGNAL_SHARDS_FLAG,
    SINGLE_PULL_COST,
    TEN_PULL_COST,
    SR_CONSOLIDATED_RATE,
    SR_BASE_RATE,
    SR_HARD_PITY,
    SSR_BASE_RATE,
    SSR_CONSOLIDATED_RATE,
    SSR_HARD_PITY,
    SSR_SOFT_PITY_START,
    SSR_SOFT_PITY_STEP,
    Banner,
    RewardEntry,
    banner_from_dict,
    banner_to_dict,
    build_phase_banners,
    get_banner_release,
    get_ssr_hard_pity,
    get_ssr_soft_pity_start,
    get_ssr_soft_pity_step,
    list_banner_releases,
)
from .event_items import is_gacha_event_item


DUPLICATE_SSR_PULLS = 5
DUPLICATE_SSR_SHARDS = SINGLE_PULL_COST * DUPLICATE_SSR_PULLS
SIGNAL_SHARDS_REWARD_NAME = "Осколки сигнала"
SIGNAL_SHARDS_CURRENCY = "signal_shards"
RESONANCE_DUST_CURRENCY = "resonance_dust"
RESONANCE_MARKS_CURRENCY = "resonance_marks"
RESONANCE_DUST_NAME = "Пыль резонанса"
RESONANCE_MARKS_NAME = "Знаки резонанса"
TICKET_NAMES = {
    "weapon": "Оружейный отклик",
    "outfit": "Отклик снаряжения",
}
TICKET_SHARD_COST = SINGLE_PULL_COST
DUST_PER_PULL = 15
MARKS_PER_SR = 1
MARKS_PER_SSR = 25
DUST_TICKET_PRICE = 75
MARK_TICKET_PRICE = 5
MONTHLY_DUST_TICKET_LIMIT = 5
EVENT_SHARDS_DAILY_CAP = 80
COMBAT_SHARDS_DAILY_CAP = 120
WEEKLY_QUEST_SHARDS_TARGET = 5
WEEKLY_QUEST_SHARDS_REWARD = 400
RESONANCE_HISTORY_RUNTIME_KEY = "resonance_history"
RESONANCE_HISTORY_LIMIT_PER_BANNER = 50
PUBLIC_LAUNCH_SETTING = "resonance_public_launch_v1"
PUBLIC_LAUNCH_NOTICE_SETTING = "resonance_public_launch_notice_v2"
PUBLIC_LAUNCH_REWARD_SETTING = "resonance_public_launch_reward_v1"
PUBLIC_LAUNCH_REWARD_STATE_KEY = "resonance_public_launch_reward_v1"
PUBLIC_LAUNCH_REWARD_SHARDS = TEN_PULL_COST
BANNER_SNAPSHOT_SETTING_PREFIX = "resonance_banner_snapshot"
ACTIVE_BANNER_RELEASE_SETTING = "resonance_active_banner_release"
SCHEDULED_BANNER_RELEASE_SETTING = "resonance_scheduled_banner_release"
SIGNAL_SHARD_BOOST_SETTING = "resonance_signal_shard_boost"
logger = logging.getLogger(__name__)


def _today_ordinal() -> int:
    return datetime.now(timezone.utc).toordinal()


def _current_week_id(now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    iso = current.isocalendar()
    return int(iso.year) * 100 + int(iso.week)


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
    sr_featured: bool = False
    sr_guaranteed: bool = False
    sr_rateup_lost: bool = False
    pity_count: int = 0
    destination: str = ""


def is_resonance_enabled() -> bool:
    value = database.get_game_setting(GACHA_ENABLED_SETTING, default="1")
    return str(value) == "1"


def set_resonance_enabled(enabled: bool) -> None:
    database.set_game_setting(GACHA_ENABLED_SETTING, "1" if enabled else "0")
    if enabled:
        ensure_banner_cycle()


def ensure_resonance_public_launch() -> None:
    """
    One-time migration from admin-only test mode to public availability.
    After this runs, the admin on/off command remains authoritative.
    """
    marker = database.get_game_setting(PUBLIC_LAUNCH_SETTING, default="0")
    if str(marker) == "1":
        return
    database.set_game_setting(GACHA_ENABLED_SETTING, "1")
    database.set_game_setting(PUBLIC_LAUNCH_SETTING, "1")
    ensure_banner_cycle()


def format_resonance_launch_notice() -> str:
    return (
        "📡 ГОРОДСКОЕ ОПОВЕЩЕНИЕ\n\n"
        "После последнего сдвига фона старый приёмный блок в Убежище вышел на устойчивую частоту.\n"
        "Техники считают, что Зона начала отдавать остаточные слепки вещей, застрявших в её шуме: "
        "оружие, броню и снаряжение.\n\n"
        "Самовольный запуск оборудования вне экранированных помещений запрещён. "
        "Для работы с сигналом используйте только стабилизированный узел Убежища.\n\n"
        "Для допуска к приёмнику требуются запечатанные отклики. Их можно собрать из осколков сигнала "
        "в мастерской или приобрести у Барыги на Чёрном рынке, если товар есть в его резонансной коробке.\n\n"
        "Первым сталкерам города выдан аварийный резерв: 1600 осколков сигнала на проверку узла. "
        "Резерв зачислен поверх уже найденных осколков.\n\n"
        "Доступ к узлу открыт через раздел Убежища: Резонанс."
    )


def _grant_public_launch_reward_once(vk_id: int) -> bool:
    state = database.get_runtime_state(vk_id, PUBLIC_LAUNCH_REWARD_STATE_KEY) or {}
    if state.get("granted"):
        return False

    balance = add_signal_shards(
        vk_id,
        PUBLIC_LAUNCH_REWARD_SHARDS,
        source="public_resonance_launch",
        details={"amount": PUBLIC_LAUNCH_REWARD_SHARDS, "notice": PUBLIC_LAUNCH_NOTICE_SETTING},
    )
    database.set_runtime_state(
        vk_id,
        PUBLIC_LAUNCH_REWARD_STATE_KEY,
        {"granted": True, "amount": PUBLIC_LAUNCH_REWARD_SHARDS, "balance": balance},
    )
    return True


def send_resonance_launch_notice_once(vk) -> dict:
    """Отправить городское оповещение о запуске Резонанса один раз."""
    if not is_resonance_enabled():
        return {"sent": 0, "errors": 0, "rewarded": 0, "reward_errors": 0, "skipped": True}

    notice_sent = str(database.get_game_setting(PUBLIC_LAUNCH_NOTICE_SETTING, default="0")) == "1"
    reward_done = str(database.get_game_setting(PUBLIC_LAUNCH_REWARD_SETTING, default="0")) == "1"
    if notice_sent and reward_done:
        return {"sent": 0, "errors": 0, "rewarded": 0, "reward_errors": 0, "skipped": True}

    players = list(database.get_all_active_players())
    message = format_resonance_launch_notice()
    sent = 0
    errors = 0
    rewarded = 0
    reward_errors = 0
    for row in players:
        vk_id = int(row.get("vk_id") or 0)
        if vk_id <= 0:
            continue
        if not reward_done:
            try:
                if _grant_public_launch_reward_once(vk_id):
                    rewarded += 1
            except Exception:
                reward_errors += 1
                logger.warning("Не удалось выдать стартовый резерв Резонанса игроку %s", vk_id, exc_info=True)
                continue
        if notice_sent:
            continue
        try:
            vk.messages.send(user_id=vk_id, message=message, random_id=0)
            sent += 1
        except Exception:
            errors += 1
            logger.warning("Не удалось отправить оповещение о запуске Резонанса игроку %s", vk_id, exc_info=True)

    if not reward_done and reward_errors == 0:
        database.set_game_setting(PUBLIC_LAUNCH_REWARD_SETTING, "1")
    if not notice_sent:
        database.set_game_setting(PUBLIC_LAUNCH_NOTICE_SETTING, "1")
    return {"sent": sent, "errors": errors, "rewarded": rewarded, "reward_errors": reward_errors, "skipped": False}


def is_resonance_available(vk_id: int) -> bool:
    return is_resonance_enabled()


def get_signal_shards(vk_id: int) -> int:
    return database.get_gacha_currency_balance(vk_id, SIGNAL_SHARDS_CURRENCY, legacy_flag=SIGNAL_SHARDS_FLAG)


def get_resonance_dust(vk_id: int) -> int:
    return database.get_gacha_currency_balance(vk_id, RESONANCE_DUST_CURRENCY)


def get_resonance_marks(vk_id: int) -> int:
    return database.get_gacha_currency_balance(vk_id, RESONANCE_MARKS_CURRENCY)


def add_signal_shards(vk_id: int, amount: int, source: str = "grant", details: dict | None = None) -> int:
    safe_amount = int(amount or 0)
    result = database.change_gacha_currency(
        vk_id,
        SIGNAL_SHARDS_CURRENCY,
        safe_amount,
        source=source,
        details=details,
        legacy_flag=SIGNAL_SHARDS_FLAG,
    )
    return max(0, int(result.get("balance", 0) or 0))


def add_resonance_dust(vk_id: int, amount: int, source: str = "pull", details: dict | None = None) -> int:
    result = database.change_gacha_currency(
        vk_id,
        RESONANCE_DUST_CURRENCY,
        int(amount or 0),
        source=source,
        details=details,
    )
    return max(0, int(result.get("balance", 0) or 0))


def add_resonance_marks(vk_id: int, amount: int, source: str = "pull", details: dict | None = None) -> int:
    result = database.change_gacha_currency(
        vk_id,
        RESONANCE_MARKS_CURRENCY,
        int(amount or 0),
        source=source,
        details=details,
    )
    return max(0, int(result.get("balance", 0) or 0))


def get_ticket_name(banner_id: str) -> str | None:
    return TICKET_NAMES.get(str(banner_id or "").strip().lower())


def get_ticket_count(vk_id: int, banner_id: str) -> int:
    ticket_name = get_ticket_name(banner_id)
    if not ticket_name:
        return 0
    try:
        for row in database.get_user_inventory(vk_id):
            if row.get("name") == ticket_name:
                return max(0, int(row.get("quantity", 0) or 0))
    except Exception:
        return 0
    return 0


def convert_signal_shards_to_tickets(vk_id: int, banner_id: str, quantity: int) -> dict:
    """Собрать предметы-отклики из сырой валюты Резонанса."""
    safe_banner = str(banner_id or "").strip().lower()
    ticket_name = get_ticket_name(safe_banner)
    safe_qty = max(1, int(quantity or 1))
    if not ticket_name:
        return {"success": False, "message": "Неизвестный тип отклика.", "converted": 0}

    cost = safe_qty * TICKET_SHARD_COST
    spend = database.change_gacha_currency(
        vk_id,
        SIGNAL_SHARDS_CURRENCY,
        -cost,
        source="ticket_convert",
        details={"banner_id": safe_banner, "ticket": ticket_name, "quantity": safe_qty},
        legacy_flag=SIGNAL_SHARDS_FLAG,
    )
    if not spend.get("success"):
        return {"success": False, "message": spend.get("message") or "Не хватает осколков сигнала.", "converted": 0}

    if not database.add_item_to_inventory(vk_id, ticket_name, safe_qty):
        database.change_gacha_currency(
            vk_id,
            SIGNAL_SHARDS_CURRENCY,
            cost,
            source="ticket_convert_refund",
            details={"banner_id": safe_banner, "ticket": ticket_name, "quantity": safe_qty},
            legacy_flag=SIGNAL_SHARDS_FLAG,
        )
        return {"success": False, "message": f"Не удалось выдать предмет '{ticket_name}'. Осколки возвращены.", "converted": 0}

    return {
        "success": True,
        "message": f"Собрано: {ticket_name} x{safe_qty}.",
        "converted": safe_qty,
        "ticket": ticket_name,
        "shards_spent": cost,
        "shards_left": max(0, int(spend.get("balance", 0) or 0)),
        "tickets_left": get_ticket_count(vk_id, safe_banner),
    }


def _ensure_pull_tickets(vk_id: int, banner_id: str, count: int) -> dict:
    ticket_name = get_ticket_name(banner_id)
    safe_count = max(1, int(count or 1))
    if not ticket_name:
        return {"success": False, "message": "Неизвестный тип отклика."}
    current = get_ticket_count(vk_id, banner_id)
    converted = 0
    if current < safe_count:
        missing = safe_count - current
        conversion = convert_signal_shards_to_tickets(vk_id, banner_id, missing)
        if not conversion.get("success"):
            return {
                "success": False,
                "message": (
                    f"Не хватает предметов '{ticket_name}': нужно {safe_count}, у тебя {current}. "
                    f"Автосборка из осколков не прошла: {conversion.get('message', 'ошибка')}"
                ),
            }
        converted = int(conversion.get("converted", 0) or 0)

    if not database.remove_item_from_inventory(vk_id, ticket_name, safe_count):
        return {"success": False, "message": f"Не удалось списать '{ticket_name}' x{safe_count}."}
    return {
        "success": True,
        "ticket": ticket_name,
        "ticket_cost": safe_count,
        "converted": converted,
        "tickets_left": get_ticket_count(vk_id, banner_id),
        "shards_left": get_signal_shards(vk_id),
    }


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def ensure_banner_cycle(now_ts: int | None = None) -> dict:
    """Получить текущую фазу баннеров и создать её при необходимости."""
    now = int(now_ts if now_ts is not None else _now_ts())
    duration = max(1, int(BANNER_DURATION_DAYS) * 24 * 60 * 60)
    phases_per_patch = max(1, int(BANNER_PHASES_PER_PATCH))
    patch_duration = duration * phases_per_patch
    try:
        apply_due_scheduled_banner_release(now)
    except Exception:
        logger.warning("Не удалось применить отложенный релиз баннеров", exc_info=True)
    stored = int(database.get_game_setting(BANNER_CYCLE_START_SETTING, default="0") or 0)
    if stored <= 0:
        stored = now
        database.set_game_setting(BANNER_CYCLE_START_SETTING, str(stored))
        database.set_game_setting(BANNER_ROTATION_INDEX_SETTING, "0")
    elapsed = max(0, now - stored)
    expired = elapsed >= patch_duration
    phase_index = min(phases_per_patch - 1, elapsed // duration) if not expired else phases_per_patch - 1
    phase_start = stored + phase_index * duration
    end_ts = phase_start + duration
    return {
        "patch_start_ts": stored,
        "patch_end_ts": stored + patch_duration,
        "start_ts": phase_start,
        "end_ts": end_ts,
        "remaining_seconds": 0 if expired else max(0, end_ts - now),
        "duration_seconds": duration,
        "rotation_index": int(phase_index),
        "phase_index": int(phase_index),
        "phase_number": phase_index + 1,
        "phases_per_patch": phases_per_patch,
        "patch_duration_days": int(BANNER_PATCH_DURATION_DAYS),
        "expired": expired,
    }


def format_seconds_left(seconds: int) -> str:
    remaining = max(0, int(seconds or 0))
    days, rem = divmod(remaining, 24 * 60 * 60)
    hours, rem = divmod(rem, 60 * 60)
    minutes, secs = divmod(rem, 60)
    return f"{days}д {hours:02d}:{minutes:02d}:{secs:02d}"


def get_signal_shard_boost(now_ts: int | None = None) -> dict:
    """Текущее временное окно повышенного выпадения осколков."""
    now = int(now_ts if now_ts is not None else _now_ts())
    raw = database.get_game_setting(SIGNAL_SHARD_BOOST_SETTING, default="")
    if not raw:
        return {"active": False, "multiplier": 1.0, "bonus_percent": 0, "remaining_seconds": 0, "formatted": "0д 00:00:00"}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("boost setting is not dict")
    except Exception:
        logger.warning("Не удалось прочитать окно буста осколков, настройка сброшена", exc_info=True)
        database.set_game_setting(SIGNAL_SHARD_BOOST_SETTING, "")
        return {"active": False, "multiplier": 1.0, "bonus_percent": 0, "remaining_seconds": 0, "formatted": "0д 00:00:00"}

    multiplier = max(1.0, float(data.get("multiplier") or 1.0))
    end_ts = int(data.get("end_ts") or 0)
    if multiplier <= 1.0 or end_ts <= now:
        database.set_game_setting(SIGNAL_SHARD_BOOST_SETTING, "")
        return {"active": False, "multiplier": 1.0, "bonus_percent": 0, "remaining_seconds": 0, "formatted": "0д 00:00:00"}

    remaining = max(0, end_ts - now)
    return {
        "active": True,
        "name": str(data.get("name") or "Резонансный фон"),
        "multiplier": multiplier,
        "bonus_percent": int(round((multiplier - 1.0) * 100)),
        "start_ts": int(data.get("start_ts") or 0),
        "end_ts": end_ts,
        "remaining_seconds": remaining,
        "formatted": format_seconds_left(remaining),
    }


def set_signal_shard_boost(multiplier: float, duration_minutes: int, name: str | None = None) -> dict:
    safe_multiplier = max(1.0, float(multiplier or 1.0))
    safe_minutes = max(0, int(duration_minutes or 0))
    if safe_multiplier <= 1.0 or safe_minutes <= 0:
        database.set_game_setting(SIGNAL_SHARD_BOOST_SETTING, "")
        return get_signal_shard_boost()
    now = _now_ts()
    payload = {
        "name": str(name or "Резонансный фон")[:80],
        "multiplier": safe_multiplier,
        "start_ts": now,
        "end_ts": now + safe_minutes * 60,
    }
    database.set_game_setting(SIGNAL_SHARD_BOOST_SETTING, json.dumps(payload, ensure_ascii=False))
    return get_signal_shard_boost(now)


def clear_signal_shard_boost() -> dict:
    database.set_game_setting(SIGNAL_SHARD_BOOST_SETTING, "")
    return get_signal_shard_boost()


def _boost_signal_shard_amount(amount: int, boost: dict) -> int:
    base = max(0, int(amount or 0))
    if base <= 0 or not boost.get("active"):
        return base
    multiplier = max(1.0, float(boost.get("multiplier") or 1.0))
    return max(base + 1, int(round(base * multiplier)))


def _apply_signal_shard_boost(amount: int, cap: int = 0) -> tuple[int, int, dict]:
    boost = get_signal_shard_boost()
    boosted_amount = _boost_signal_shard_amount(amount, boost)
    boosted_cap = _boost_signal_shard_amount(cap, boost) if int(cap or 0) > 0 else max(0, int(cap or 0))
    return boosted_amount, boosted_cap, boost


def get_banner_time_left() -> dict:
    cycle = ensure_banner_cycle()
    return {**cycle, "formatted": format_seconds_left(cycle["remaining_seconds"])}


def _snapshot_key(cycle_start_ts: int) -> str:
    return f"{BANNER_SNAPSHOT_SETTING_PREFIX}_{int(cycle_start_ts)}"


def _release_to_banners(release: dict | None, phase_index: int = 0) -> dict[str, Banner]:
    if not release:
        return {}
    phases = release.get("phases") or ()
    if phases:
        safe_index = max(0, min(len(phases) - 1, int(phase_index or 0)))
        banners = phases[safe_index]
    else:
        banners = release.get("banners") or {}
    return {str(key): value for key, value in banners.items() if isinstance(value, Banner)}


def _banner_release_summary(release: dict) -> dict:
    phases = release.get("phases") or ()
    first = _release_to_banners(release, 0)
    second = _release_to_banners(release, 1) if len(phases) > 1 else {}
    return {
        "id": release.get("id"),
        "name": release.get("name"),
        "patch": int(release.get("patch", 0) or 0),
        "phase": 0,
        "phases": len(phases) or 1,
        "weapon": first.get("weapon").name if first.get("weapon") else "-",
        "outfit": first.get("outfit").name if first.get("outfit") else "-",
        "weapon_phase_2": second.get("weapon").name if second.get("weapon") else "-",
        "outfit_phase_2": second.get("outfit").name if second.get("outfit") else "-",
    }


def get_available_banner_releases() -> list[dict]:
    """Вернуть подготовленные в коде релизы баннеров для админки."""
    return [_banner_release_summary(release) for release in list_banner_releases()]


def _get_scheduled_banner_release() -> dict | None:
    raw = database.get_game_setting(SCHEDULED_BANNER_RELEASE_SETTING, default="")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    release_id = str(data.get("release_id") or "").strip().lower()
    start_ts = int(data.get("start_ts", 0) or 0)
    if not release_id or start_ts <= 0:
        return None
    release = get_banner_release(release_id)
    if not release:
        return None
    return {
        "release_id": release_id,
        "release_name": release.get("name") or release_id,
        "start_ts": start_ts,
    }


def get_banner_release_admin_status(now_ts: int | None = None) -> dict:
    """Короткий статус ручной ротации баннеров."""
    raw_cycle = ensure_banner_cycle(now_ts=now_ts)
    cycle = {**raw_cycle, "formatted": format_seconds_left(raw_cycle["remaining_seconds"])}
    active_id = str(database.get_game_setting(ACTIVE_BANNER_RELEASE_SETTING, default="") or "")
    active_release = get_banner_release(active_id)
    scheduled = _get_scheduled_banner_release()
    return {
        "cycle": cycle,
        "active": _banner_release_summary(active_release) if active_release else {"id": active_id or "-", "name": active_id or "Снапшот текущего цикла"},
        "scheduled": scheduled,
        "available": get_available_banner_releases(),
    }


def _serialize_banners(banners: dict[str, Banner]) -> str:
    payload = {
        banner_id: banner_to_dict(banner)
        for banner_id, banner in banners.items()
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _deserialize_banners(raw: str | None) -> dict[str, Banner]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}

    result: dict[str, Banner] = {}
    for banner_id, banner_data in data.items():
        if not isinstance(banner_data, dict):
            continue
        banner = banner_from_dict(banner_data)
        if banner.id:
            result[str(banner_id)] = banner
    return result


def activate_banner_release(release_id: str, start_ts: int | None = None) -> dict:
    """Включить подготовленный патч баннеров как новый активный цикл."""
    safe_id = str(release_id or "").strip().lower()
    release = get_banner_release(safe_id)
    if not release:
        return {"success": False, "message": f"Неизвестный релиз баннеров: {release_id}"}
    phases = release.get("phases") or ()
    if len(phases) < max(1, int(BANNER_PHASES_PER_PATCH)):
        return {"success": False, "message": "Релиз патча должен содержать две фазы баннеров."}
    first_phase = _release_to_banners(release, 0)
    if set(first_phase) != {"weapon", "outfit"}:
        return {"success": False, "message": "Каждая фаза релиза должна содержать ровно два баннера: weapon и outfit."}

    cycle_start = int(start_ts if start_ts is not None else _now_ts())
    database.set_game_setting(BANNER_CYCLE_START_SETTING, str(cycle_start))
    database.set_game_setting(BANNER_ROTATION_INDEX_SETTING, "0")
    database.set_game_setting(ACTIVE_BANNER_RELEASE_SETTING, safe_id)
    duration = max(1, int(BANNER_DURATION_DAYS) * 24 * 60 * 60)
    for index in range(max(1, int(BANNER_PHASES_PER_PATCH))):
        phase_banners = _release_to_banners(release, index)
        if set(phase_banners) != {"weapon", "outfit"}:
            return {"success": False, "message": f"Фаза {index + 1} релиза должна содержать weapon и outfit."}
        phase_start = cycle_start + index * duration
        database.set_game_setting(_snapshot_key(phase_start), _serialize_banners(phase_banners))
        database.set_gacha_banner_snapshots(
            phase_start,
            {banner_id: banner_to_dict(banner) for banner_id, banner in phase_banners.items()},
        )
    return {
        "success": True,
        "release_id": safe_id,
        "release_name": release.get("name") or safe_id,
        "start_ts": cycle_start,
        "end_ts": cycle_start + duration * max(1, int(BANNER_PHASES_PER_PATCH)),
        "banners": [_banner_release_summary(release)],
    }


def schedule_banner_release(release_id: str, start_ts: int) -> dict:
    """Поставить подготовленный релиз баннеров на отложенный старт."""
    safe_id = str(release_id or "").strip().lower()
    release = get_banner_release(safe_id)
    if not release:
        return {"success": False, "message": f"Неизвестный релиз баннеров: {release_id}"}
    safe_start = int(start_ts or 0)
    if safe_start <= 0:
        return {"success": False, "message": "Нужно указать корректное время старта."}
    payload = {"release_id": safe_id, "start_ts": safe_start}
    database.set_game_setting(SCHEDULED_BANNER_RELEASE_SETTING, json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return {
        "success": True,
        "release_id": safe_id,
        "release_name": release.get("name") or safe_id,
        "start_ts": safe_start,
    }


def cancel_scheduled_banner_release() -> dict:
    scheduled = _get_scheduled_banner_release()
    database.set_game_setting(SCHEDULED_BANNER_RELEASE_SETTING, "")
    return {
        "success": True,
        "cancelled": bool(scheduled),
        "release_id": scheduled.get("release_id") if scheduled else "",
        "start_ts": scheduled.get("start_ts") if scheduled else 0,
    }


def apply_due_scheduled_banner_release(now_ts: int | None = None) -> dict:
    now = int(now_ts if now_ts is not None else _now_ts())
    scheduled = _get_scheduled_banner_release()
    if not scheduled:
        return {"success": False, "applied": False, "message": "Отложенного релиза нет."}
    if now < int(scheduled["start_ts"]):
        return {"success": True, "applied": False, **scheduled}
    result = activate_banner_release(scheduled["release_id"], start_ts=scheduled["start_ts"])
    if result.get("success"):
        database.set_game_setting(SCHEDULED_BANNER_RELEASE_SETTING, "")
        return {"success": True, "applied": True, **scheduled}
    return {"success": False, "applied": False, "message": result.get("message", "Не удалось включить релиз."), **scheduled}


def get_active_banners(now_ts: int | None = None) -> dict[str, Banner]:
    """
    Вернуть сохранённый пул текущей фазы.

    Снапшот фиксирует состав баннера на старт фазы: если пул в коде расширится,
    уже активная волна не поменяется задним числом, а новые/старые предметы
    смогут вернуться в следующих фазах.
    """
    cycle = ensure_banner_cycle(now_ts=now_ts)
    if cycle.get("expired"):
        return {}
    key = _snapshot_key(cycle["start_ts"])
    snapshot_payload = database.get_gacha_banner_snapshots(cycle["start_ts"])
    banners = _deserialize_banners(json.dumps(snapshot_payload, ensure_ascii=False) if snapshot_payload else None)
    if banners:
        return banners

    stored = database.get_game_setting(key, default="")
    banners = _deserialize_banners(stored)
    if banners:
        database.set_gacha_banner_snapshots(
            cycle["start_ts"],
            {banner_id: banner_to_dict(banner) for banner_id, banner in banners.items()},
        )
        return banners

    active_id = str(database.get_game_setting(ACTIVE_BANNER_RELEASE_SETTING, default="") or "").strip().lower()
    active_release = get_banner_release(active_id)
    banners = _release_to_banners(active_release, cycle["phase_index"]) if active_release else build_phase_banners(cycle["phase_index"])
    serialized = _serialize_banners(banners)
    database.set_gacha_banner_snapshots(
        cycle["start_ts"],
        {banner_id: banner_to_dict(banner) for banner_id, banner in banners.items()},
    )
    database.set_game_setting(key, serialized)
    return banners


def get_banner(banner_id: str) -> Banner | None:
    return get_active_banners().get(str(banner_id or "").strip().lower())


def add_signal_shards_capped(vk_id: int, amount: int, source: str, daily_cap: int) -> dict:
    """Начислить осколки с дневным лимитом по источнику."""
    base_amount = max(0, int(amount or 0))
    base_cap = max(0, int(daily_cap or 0))
    safe_amount, safe_cap, boost = _apply_signal_shard_boost(base_amount, base_cap)
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

    details = {"cap": safe_cap, "used_before": used, "base_amount": base_amount, "base_cap": base_cap}
    if boost.get("active"):
        details["boost"] = {
            "name": boost.get("name"),
            "multiplier": boost.get("multiplier"),
            "bonus_percent": boost.get("bonus_percent"),
        }
    balance = add_signal_shards(vk_id, grant, source=f"{key}_reward", details=details)
    database.set_user_flag(vk_id, day_flag, today)
    database.set_user_flag(vk_id, used_flag, used + grant)
    return {"granted": grant, "balance": balance, "cap": safe_cap, "used": used + grant, "boost": boost}


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
    base_amount = amount
    amount, _cap, boost = _apply_signal_shard_boost(base_amount, 0)
    details = {"streak": safe_streak, "base_amount": base_amount}
    if boost.get("active"):
        details["boost"] = {
            "name": boost.get("name"),
            "multiplier": boost.get("multiplier"),
            "bonus_percent": boost.get("bonus_percent"),
        }
    return {"granted": amount, "balance": add_signal_shards(vk_id, amount, source="daily_quest", details=details), "cap": 0, "used": 0, "boost": boost}


def get_weekly_quest_shards_status(vk_id: int) -> dict:
    week_id = _current_week_id()
    stored_week = int(database.get_user_flag(vk_id, "resonance_weekly_quest_shards_week", 0) or 0)
    if stored_week != week_id:
        return {
            "week_id": week_id,
            "count": 0,
            "target": WEEKLY_QUEST_SHARDS_TARGET,
            "claimed": False,
            "reward": WEEKLY_QUEST_SHARDS_REWARD,
        }
    return {
        "week_id": week_id,
        "count": max(0, int(database.get_user_flag(vk_id, "resonance_weekly_quest_shards_count", 0) or 0)),
        "target": WEEKLY_QUEST_SHARDS_TARGET,
        "claimed": bool(int(database.get_user_flag(vk_id, "resonance_weekly_quest_shards_claimed", 0) or 0)),
        "reward": WEEKLY_QUEST_SHARDS_REWARD,
    }


def grant_weekly_quest_shards(vk_id: int) -> dict:
    """Недельная цель: несколько забранных daily-наград за UTC-неделю."""
    week_id = _current_week_id()
    status = get_weekly_quest_shards_status(vk_id)
    count = int(status.get("count", 0) or 0) + 1
    database.set_user_flag(vk_id, "resonance_weekly_quest_shards_week", week_id)
    database.set_user_flag(vk_id, "resonance_weekly_quest_shards_count", count)

    if status.get("claimed"):
        return {**status, "count": count, "granted": 0, "balance": get_signal_shards(vk_id)}
    if count < WEEKLY_QUEST_SHARDS_TARGET:
        return {**status, "count": count, "claimed": False, "granted": 0, "balance": get_signal_shards(vk_id)}

    base_amount = WEEKLY_QUEST_SHARDS_REWARD
    amount, _cap, boost = _apply_signal_shard_boost(base_amount, 0)
    details = {"week_id": week_id, "count": count, "target": WEEKLY_QUEST_SHARDS_TARGET, "base_amount": base_amount}
    if boost.get("active"):
        details["boost"] = {
            "name": boost.get("name"),
            "multiplier": boost.get("multiplier"),
            "bonus_percent": boost.get("bonus_percent"),
        }
    balance = add_signal_shards(vk_id, amount, source="weekly_quest", details=details)
    database.set_user_flag(vk_id, "resonance_weekly_quest_shards_claimed", 1)
    return {
        "week_id": week_id,
        "count": count,
        "target": WEEKLY_QUEST_SHARDS_TARGET,
        "claimed": True,
        "reward": WEEKLY_QUEST_SHARDS_REWARD,
        "granted": amount,
        "balance": balance,
        "boost": boost,
    }


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


def _exchange_shop_period_key(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.strftime("%Y%m")


def _dust_shop_key(banner_id: str) -> str:
    return f"dust_ticket_{str(banner_id or '').strip().lower()}"


def get_exchange_wallet(vk_id: int) -> dict:
    return {
        "shards": get_signal_shards(vk_id),
        "dust": get_resonance_dust(vk_id),
        "marks": get_resonance_marks(vk_id),
        "weapon_tickets": get_ticket_count(vk_id, "weapon"),
        "outfit_tickets": get_ticket_count(vk_id, "outfit"),
    }


def get_exchange_shop(vk_id: int) -> dict:
    period_key = _exchange_shop_period_key()
    dust_items = []
    for banner_id, ticket_name in TICKET_NAMES.items():
        bought = database.get_gacha_shop_purchase_count(vk_id, period_key, _dust_shop_key(banner_id))
        dust_items.append({
            "banner_id": banner_id,
            "ticket": ticket_name,
            "price": DUST_TICKET_PRICE,
            "limit": MONTHLY_DUST_TICKET_LIMIT,
            "bought": min(MONTHLY_DUST_TICKET_LIMIT, max(0, int(bought or 0))),
            "left": max(0, MONTHLY_DUST_TICKET_LIMIT - max(0, int(bought or 0))),
        })
    mark_items = [
        {
            "banner_id": banner_id,
            "ticket": ticket_name,
            "price": MARK_TICKET_PRICE,
        }
        for banner_id, ticket_name in TICKET_NAMES.items()
    ]
    return {
        "period_key": period_key,
        "wallet": get_exchange_wallet(vk_id),
        "dust_items": dust_items,
        "mark_items": mark_items,
    }


def buy_exchange_tickets(vk_id: int, banner_id: str, currency: str, quantity: int) -> dict:
    safe_banner = str(banner_id or "").strip().lower()
    ticket_name = get_ticket_name(safe_banner)
    safe_currency = str(currency or "").strip().lower()
    safe_qty = max(1, int(quantity or 1))
    if not ticket_name:
        return {"success": False, "message": "Неизвестный тип отклика."}
    if safe_currency not in {"dust", "marks"}:
        return {"success": False, "message": "Неизвестная валюта обменника."}

    period_key = _exchange_shop_period_key()
    source_currency = RESONANCE_DUST_CURRENCY if safe_currency == "dust" else RESONANCE_MARKS_CURRENCY
    price = DUST_TICKET_PRICE if safe_currency == "dust" else MARK_TICKET_PRICE
    if safe_currency == "dust":
        bought = database.get_gacha_shop_purchase_count(vk_id, period_key, _dust_shop_key(safe_banner))
        left = max(0, MONTHLY_DUST_TICKET_LIMIT - int(bought or 0))
        if safe_qty > left:
            return {"success": False, "message": f"Месячный лимит: осталось {left} шт."}

    spend = database.change_gacha_currency(
        vk_id,
        source_currency,
        -(price * safe_qty),
        source="exchange_shop",
        details={"banner_id": safe_banner, "ticket": ticket_name, "quantity": safe_qty, "section": safe_currency},
    )
    if not spend.get("success"):
        currency_name = RESONANCE_DUST_NAME if safe_currency == "dust" else RESONANCE_MARKS_NAME
        return {"success": False, "message": f"Не хватает валюты '{currency_name}'."}

    if not database.add_item_to_inventory(vk_id, ticket_name, safe_qty):
        database.change_gacha_currency(
            vk_id,
            source_currency,
            price * safe_qty,
            source="exchange_shop_refund",
            details={"banner_id": safe_banner, "ticket": ticket_name, "quantity": safe_qty, "section": safe_currency},
        )
        return {"success": False, "message": f"Не удалось выдать '{ticket_name}'. Валюта возвращена."}

    if safe_currency == "dust":
        database.add_gacha_shop_purchase_count(vk_id, period_key, _dust_shop_key(safe_banner), safe_qty)

    return {
        "success": True,
        "message": f"Куплено: {ticket_name} x{safe_qty}.",
        "ticket": ticket_name,
        "quantity": safe_qty,
        "wallet": get_exchange_wallet(vk_id),
        "shop": get_exchange_shop(vk_id),
    }


def _grant_pull_exchange_currencies(vk_id: int, banner_id: str, rewards: list[PullReward]) -> dict:
    dust = DUST_PER_PULL * len(rewards)
    marks = 0
    for reward in rewards:
        if reward.rarity == "SSR":
            marks += MARKS_PER_SSR
        elif reward.rarity == "SR":
            marks += MARKS_PER_SR
    dust_balance = add_resonance_dust(
        vk_id,
        dust,
        source="pull_reward",
        details={"banner_id": banner_id, "pulls": len(rewards)},
    ) if dust else get_resonance_dust(vk_id)
    marks_balance = add_resonance_marks(
        vk_id,
        marks,
        source="pull_reward",
        details={"banner_id": banner_id, "pulls": len(rewards)},
    ) if marks else get_resonance_marks(vk_id)
    return {
        "dust": dust,
        "dust_balance": dust_balance,
        "marks": marks,
        "marks_balance": marks_balance,
    }


def _flag_name(banner_id: str, suffix: str) -> str:
    return f"resonance_{banner_id}_{suffix}"


def _get_banner_state(vk_id: int, banner_id: str) -> dict:
    return database.get_gacha_user_state(vk_id, banner_id, legacy_flags={
        "pity_ssr": _flag_name(banner_id, "pity_ssr"),
        "pity_sr": _flag_name(banner_id, "pity_sr"),
        "featured_guaranteed": _flag_name(banner_id, "featured_guaranteed"),
        "featured_sr_guaranteed": _flag_name(banner_id, "featured_sr_guaranteed"),
    })


def _save_banner_state(vk_id: int, banner_id: str, state: dict) -> None:
    database.set_gacha_user_state(vk_id, banner_id, state, legacy_flags={
        "pity_ssr": _flag_name(banner_id, "pity_ssr"),
        "pity_sr": _flag_name(banner_id, "pity_sr"),
        "featured_guaranteed": _flag_name(banner_id, "featured_guaranteed"),
        "featured_sr_guaranteed": _flag_name(banner_id, "featured_sr_guaranteed"),
    })


def get_banner_state(vk_id: int, banner_id: str) -> dict:
    banner = get_banner(banner_id)
    if not banner:
        raise ValueError("unknown banner")
    return _get_banner_state(vk_id, banner.id)


def get_rate_disclosure() -> dict:
    """Public rates shown to players: base odds plus approximate odds with pity."""
    return {
        "ssr_base_rate": SSR_BASE_RATE,
        "ssr_consolidated_rate": SSR_CONSOLIDATED_RATE,
        "featured_ssr_consolidated_rate": FEATURED_SSR_CONSOLIDATED_RATE,
        "sr_base_rate": SR_BASE_RATE,
        "sr_consolidated_rate": SR_CONSOLIDATED_RATE,
        "ssr_hard_pity": SSR_HARD_PITY,
        "sr_hard_pity": SR_HARD_PITY,
        "ssr_soft_pity_start": SSR_SOFT_PITY_START,
        "ssr_soft_pity_step": SSR_SOFT_PITY_STEP,
    }


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


def _owned_featured_candidates(vk_id: int, banner: Banner) -> tuple[str, ...]:
    """Featured SSR candidates, excluding set pieces the player already owns."""
    featured = tuple(banner.featured_ssr or ())
    if banner.id != "outfit" or len(featured) <= 1:
        return featured
    missing = tuple(item_name for item_name in featured if not _has_item(vk_id, item_name))
    return missing or featured


def _grant_item_to_storage(vk_id: int, item_name: str, quantity: int = 1) -> bool:
    return bool(database.add_item_to_storage(vk_id, item_name, quantity))


def _grant_item_to_inventory(vk_id: int, item_name: str, quantity: int = 1) -> bool:
    return bool(database.add_item_to_inventory(vk_id, item_name, quantity))


def _inventory_weight(vk_id: int) -> float:
    total = 0.0
    for row in database.get_user_inventory(vk_id):
        total += float(row.get("weight", 0) or 0) * int(row.get("quantity", 0) or 0)
    return round(total, 3)


def _item_weight(item_name: str, quantity: int = 1) -> float:
    item = database.get_item_by_name(item_name) or {}
    return round(float(item.get("weight", 0) or 0) * max(1, int(quantity or 1)), 3)


def _can_fit_inventory(vk_id: int, item_name: str, quantity: int = 1) -> bool:
    user = database.get_user_by_vk(vk_id) or {}
    max_weight = float(user.get("max_weight", 0) or 0)
    if max_weight <= 0:
        return True
    return _inventory_weight(vk_id) + _item_weight(item_name, quantity) <= max_weight + 1e-6


def _grant_item_to_inventory_or_storage(vk_id: int, item_name: str, quantity: int = 1) -> str:
    """Выдать ценный предмет без наказания за перевес: рюкзак, иначе шкаф."""
    if _can_fit_inventory(vk_id, item_name, quantity) and _grant_item_to_inventory(vk_id, item_name, quantity):
        return "inventory"
    if _grant_item_to_storage(vk_id, item_name, quantity):
        return "storage_overweight"
    return "failed"


def _grant_reward(vk_id: int, reward: PullReward) -> PullReward:
    if reward.kind == "shells":
        ok, _ = database.add_shells(vk_id, reward.quantity)
        if ok:
            return reward
        fallback = PullReward(reward.rarity, "Металлолом", max(1, reward.quantity // 3), kind="item")
        _grant_item_to_storage(vk_id, fallback.name, fallback.quantity)
        return fallback

    if reward.rarity == "SSR" and is_gacha_event_item(reward.name) and _has_item(vk_id, reward.name):
        add_signal_shards(
            vk_id,
            DUPLICATE_SSR_SHARDS,
            source="duplicate_ssr",
            details={"source_item": reward.name, "pulls_compensation": DUPLICATE_SSR_PULLS},
        )
        return replace(
            reward,
            name=SIGNAL_SHARDS_REWARD_NAME,
            quantity=DUPLICATE_SSR_SHARDS,
            kind="currency",
            duplicate=True,
            source_name=reward.name,
        )

    if reward.rarity == "SSR" and reward.kind == "item":
        destination = _grant_item_to_inventory_or_storage(vk_id, reward.name, reward.quantity)
        return replace(reward, destination=destination)
    else:
        _grant_item_to_storage(vk_id, reward.name, reward.quantity)
    return replace(reward, destination="storage")


def _quantity(entry: RewardEntry) -> int:
    if entry.max_qty <= entry.min_qty:
        return max(1, entry.min_qty)
    return random.randint(entry.min_qty, entry.max_qty)


def _roll_entry(entry: RewardEntry, rarity: str) -> PullReward:
    return PullReward(rarity=rarity, name=entry.name, quantity=_quantity(entry), kind=entry.kind)


def _roll_ssr(banner: Banner, state: dict) -> PullReward:
    pity_count = max(1, int(state.get("pity_ssr", 1) or 1))
    featured_choices = tuple(state.get("featured_candidates") or banner.featured_ssr)
    if state.get("featured_guaranteed"):
        item_name = random.choice(featured_choices)
        featured = True
        guaranteed = True
        fifty_fifty_lost = False
        state["featured_guaranteed"] = False
    elif random.random() < 0.5:
        item_name = random.choice(featured_choices)
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
    if featured and banner.id == "outfit":
        candidates = tuple(state.get("featured_candidates") or ())
        remaining = tuple(item for item in candidates if item != item_name)
        state["featured_candidates"] = remaining
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
    featured_pool = tuple(banner.featured_sr or ())
    off_pool = tuple(banner.off_sr or ())
    if not featured_pool:
        return _roll_entry(random.choice(banner.sr_pool), "SR")

    if state.get("featured_sr_guaranteed"):
        reward = _roll_entry(random.choice(featured_pool), "SR")
        state["featured_sr_guaranteed"] = False
        return replace(reward, sr_featured=True, sr_guaranteed=True)
    if not off_pool or random.random() < 0.5:
        reward = _roll_entry(random.choice(featured_pool), "SR")
        return replace(reward, sr_featured=True)

    state["featured_sr_guaranteed"] = True
    reward = _roll_entry(random.choice(off_pool), "SR")
    return replace(reward, sr_rateup_lost=True)


def _roll_r(banner: Banner) -> PullReward:
    return _roll_entry(random.choice(banner.r_pool), "R")


def _current_ssr_rate(banner: Banner, pity_ssr: int) -> float:
    hard_pity = get_ssr_hard_pity(banner.id)
    soft_start = get_ssr_soft_pity_start(banner.id)
    soft_step = get_ssr_soft_pity_step(banner.id)
    if pity_ssr >= hard_pity:
        return 100.0
    if pity_ssr <= soft_start:
        return SSR_BASE_RATE
    return min(100.0, SSR_BASE_RATE + (pity_ssr - soft_start) * soft_step)


def _roll_one(banner: Banner, state: dict) -> PullReward:
    state["pity_ssr"] += 1
    state["pity_sr"] += 1

    if random.random() * 100 < _current_ssr_rate(banner, state["pity_ssr"]):
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

    ticket_spend = _ensure_pull_tickets(vk_id, banner.id, count)
    if not ticket_spend.get("success"):
        return {"success": False, "message": ticket_spend.get("message") or "Не хватает откликов."}
    state = _get_banner_state(vk_id, banner.id)
    state["featured_candidates"] = _owned_featured_candidates(vk_id, banner)
    raw_rewards = [_roll_one(banner, state) for _ in range(count)]
    state.pop("featured_candidates", None)
    rewards = [_grant_reward(vk_id, reward) for reward in raw_rewards]
    exchange_reward = _grant_pull_exchange_currencies(vk_id, banner.id, raw_rewards)
    _record_banner_stats(banner, raw_rewards)
    _save_banner_state(vk_id, banner.id, state)
    shards_left = get_signal_shards(vk_id)
    _record_pull_history(vk_id, banner, count, int(ticket_spend.get("ticket_cost", count) or count), rewards, shards_left)

    return {
        "success": True,
        "banner": banner,
        "count": count,
        "cost": int(ticket_spend.get("ticket_cost", count) or count),
        "ticket": ticket_spend.get("ticket"),
        "converted_tickets": int(ticket_spend.get("converted", 0) or 0),
        "tickets_left": int(ticket_spend.get("tickets_left", 0) or 0),
        "shards_left": shards_left,
        "exchange_reward": exchange_reward,
        "rewards": rewards,
        "state": state,
    }


def get_banners() -> tuple[Banner, ...]:
    active = get_active_banners()
    return tuple(active.get(banner_id) for banner_id in BANNERS.keys() if active.get(banner_id))


def _load_pull_history(vk_id: int) -> dict:
    data = database.get_runtime_state(vk_id, RESONANCE_HISTORY_RUNTIME_KEY) or {}
    return data if isinstance(data, dict) else {}


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
    best_rarity = "SSR" if any(r.rarity == "SSR" for r in rewards) else "SR" if any(r.rarity == "SR" for r in rewards) else "R"
    reward_rows = [
        {
            "rarity": reward.rarity,
            "name": reward.name,
            "quantity": int(reward.quantity),
            "duplicate": bool(reward.duplicate),
            "source_name": reward.source_name,
            "destination": reward.destination,
            "featured": bool(reward.featured or reward.sr_featured),
            "guaranteed": bool(reward.guaranteed or reward.sr_guaranteed),
            "rateup_lost": bool(reward.fifty_fifty_lost or reward.sr_rateup_lost),
        }
        for reward in rewards
    ]
    database.record_gacha_pull_history(
        vk_id,
        banner_id=banner.id,
        banner_name=banner.name,
        pull_count=count,
        cost=cost,
        shards_after=shards_left,
        best_rarity=best_rarity,
        rewards=reward_rows,
    )
    try:
        data = _load_pull_history(vk_id)
        rows = list(data.get(banner.id) or [])
        rows.insert(0, {
            "ts": _now_ts(),
            "banner_id": banner.id,
            "banner_name": banner.name,
            "count": int(count),
            "cost": int(cost),
            "shards_left": int(shards_left),
            "best_rarity": best_rarity,
            "rewards": reward_rows,
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
    rows = database.get_gacha_pull_history(vk_id, banner.id, limit=RESONANCE_HISTORY_LIMIT_PER_BANNER)
    if not rows:
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
    table_stats = database.get_gacha_banner_stats(cycle_start_ts, banner_id)
    if table_stats and any(int(value or 0) for value in table_stats.values()):
        return table_stats
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
        "sr_total": 0,
        "rateup_sr": 0,
        "sr_rateup_losses": 0,
        "guaranteed_rateup_sr": 0,
        "pity_sum": 0,
        "pity_count": 0,
    }
    defaults.update({key: int(value or 0) for key, value in data.items() if key in defaults})
    return defaults


def _save_stats(cycle_start_ts: int, banner_id: str, stats: dict) -> None:
    database.set_gacha_banner_stats(cycle_start_ts, banner_id, stats)
    database.set_game_setting(_stats_key(cycle_start_ts, banner_id), json.dumps(stats, ensure_ascii=False, sort_keys=True))


def _record_banner_stats(banner: Banner, rewards: list[PullReward]) -> None:
    cycle = ensure_banner_cycle()
    stats = _load_stats(cycle["start_ts"], banner.id)
    stats["pulls"] += len(rewards)
    for reward in rewards:
        if reward.rarity == "SR":
            stats["sr_total"] += 1
            if reward.sr_featured:
                stats["rateup_sr"] += 1
            if reward.sr_rateup_lost:
                stats["sr_rateup_losses"] += 1
            if reward.sr_guaranteed:
                stats["guaranteed_rateup_sr"] += 1
            continue
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
        "sr_total": 0,
        "rateup_sr": 0,
        "sr_rateup_losses": 0,
        "guaranteed_rateup_sr": 0,
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
