"""
Ограниченные глобальные ивенты.

Ивенты общие для всех игроков:
- планируются заранее;
- анонсируются за N минут;
- имеют окно активности;
- влияют на исследование/бой.
"""
from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime, timezone

from infra import config, database

logger = logging.getLogger(__name__)

_STATE_KEY = "limited_events_state_v1"
_CACHE_TTL_SEC = 15.0
_cache = {"at": 0.0, "state": None}


# Каталог ограниченных ивентов.
LIMITED_EVENTS = {
    "anomaly_surge": {
        "name": "Аномальный резонанс",
        "duration_minutes": 120,
        "announce": (
            "📢 Через 15 минут начнётся ивент «Аномальный резонанс».\n"
            "Аномальные отклики усиливаются: чаще находки и артефактные события."
        ),
        "start": (
            "⚡ ИВЕНТ НАЧАЛСЯ: «Аномальный резонанс»\n\n"
            "Зона нестабильна: шансы находок и артефактов повышены."
        ),
        "end": "⏳ Ивент «Аномальный резонанс» завершён. Показатели Зоны стабилизировались.",
        "mods": {
            "research_find_mult": 1.35,
            "research_danger_mult": 1.05,
            "artifact_event_mult": 2.00,
            "enemy_event_mult": 0.95,
            "enemy_stat_mult": 1.00,
            "combat_reward_mult": 1.10,
        },
    },
    "predator_night": {
        "name": "Час хищников",
        "duration_minutes": 90,
        "announce": (
            "📢 Через 15 минут начнётся ивент «Час хищников».\n"
            "Мутанты и охотники выходят из укрытий. Готовь усиленный комплект."
        ),
        "start": (
            "☠️ ИВЕНТ НАЧАЛСЯ: «Час хищников»\n\n"
            "Враги встречаются чаще и дерутся жёстче, но награда за бои увеличена."
        ),
        "end": "⏳ Ивент «Час хищников» завершён. Активность хищников спала.",
        "mods": {
            "research_find_mult": 1.00,
            "research_danger_mult": 1.25,
            "artifact_event_mult": 0.90,
            "enemy_event_mult": 1.70,
            "enemy_stat_mult": 1.25,
            "combat_reward_mult": 1.90,
        },
    },
    "scavenger_window": {
        "name": "Окно мародёров",
        "duration_minutes": 120,
        "announce": (
            "📢 Через 15 минут начнётся ивент «Окно мародёров».\n"
            "В Зоне откроется короткое окно добычи с повышенным шансом ценных находок."
        ),
        "start": (
            "🎒 ИВЕНТ НАЧАЛСЯ: «Окно мародёров»\n\n"
            "Шансы полезной добычи и наград за стычки увеличены."
        ),
        "end": "⏳ Ивент «Окно мародёров» завершён. Поток добычи вернулся к норме.",
        "mods": {
            "research_find_mult": 1.25,
            "research_danger_mult": 1.10,
            "artifact_event_mult": 1.35,
            "enemy_event_mult": 1.10,
            "enemy_stat_mult": 1.05,
            "combat_reward_mult": 1.35,
        },
    },
}


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _default_state(now_ts: int | None = None) -> dict:
    now = int(now_ts or _now_ts())
    nxt_id, nxt_ts = _schedule_next(now)
    return {
        "active_event_id": None,
        "active_start_ts": 0,
        "active_end_ts": 0,
        "next_event_id": nxt_id,
        "next_start_ts": nxt_ts,
        "announce_sent": False,
    }


def _schedule_next(now_ts: int) -> tuple[str, int]:
    min_m = max(30, int(getattr(config, "LIMITED_EVENT_MIN_INTERVAL_MINUTES", 300) or 300))
    max_m = max(min_m, int(getattr(config, "LIMITED_EVENT_MAX_INTERVAL_MINUTES", 540) or 540))
    delay = random.randint(min_m, max_m) * 60
    event_id = random.choice(list(LIMITED_EVENTS.keys()))
    return event_id, now_ts + delay


def _load_state(force: bool = False) -> dict:
    now = time.time()
    if not force and _cache["state"] is not None and (now - float(_cache["at"] or 0.0)) <= _CACHE_TTL_SEC:
        return dict(_cache["state"])

    raw = database.get_game_setting(_STATE_KEY, default=None)
    if not raw:
        state = _default_state()
        _save_state(state)
        return state

    try:
        state = json.loads(raw)
        if not isinstance(state, dict):
            raise ValueError("limited_events state is not dict")
    except Exception:
        logger.exception("Не удалось прочитать limited_events state, восстановление по умолчанию")
        state = _default_state()
        _save_state(state)
        return state

    # Мягкая миграция/валидация
    if state.get("next_event_id") not in LIMITED_EVENTS:
        nxt_id, nxt_ts = _schedule_next(_now_ts())
        state["next_event_id"] = nxt_id
        state["next_start_ts"] = nxt_ts
        state["announce_sent"] = False
    if state.get("active_event_id") and state.get("active_event_id") not in LIMITED_EVENTS:
        state["active_event_id"] = None
        state["active_start_ts"] = 0
        state["active_end_ts"] = 0

    _cache["state"] = dict(state)
    _cache["at"] = now
    return state


def _save_state(state: dict):
    database.set_game_setting(_STATE_KEY, json.dumps(state, ensure_ascii=False))
    _cache["state"] = dict(state)
    _cache["at"] = time.time()


def _broadcast(vk, message: str):
    players = database.get_all_active_players()
    for row in players:
        try:
            uid = int(row.get("vk_id") or 0)
            if uid <= 0:
                continue
            vk.messages.send(user_id=uid, message=message, random_id=0)
        except Exception:
            logger.warning("Не удалось отправить limited-event сообщение игроку %s", row.get("vk_id"), exc_info=True)


def limited_events_tick(vk):
    """Минутный тик планировщика ограниченных ивентов."""
    if not bool(getattr(config, "LIMITED_EVENTS_ENABLED", True)):
        return

    announce_before_min = max(1, int(getattr(config, "LIMITED_EVENT_ANNOUNCE_MINUTES", 15) or 15))
    now_ts = _now_ts()
    state = _load_state(force=True)

    active_id = state.get("active_event_id")
    active_end_ts = int(state.get("active_end_ts") or 0)

    # Активный ивент закончился
    if active_id:
        if now_ts >= active_end_ts > 0:
            ev = LIMITED_EVENTS.get(active_id, {})
            end_msg = str(ev.get("end") or f"⏳ Ивент «{ev.get('name', active_id)}» завершён.")
            _broadcast(vk, end_msg)

            nxt_id, nxt_ts = _schedule_next(now_ts)
            state.update({
                "active_event_id": None,
                "active_start_ts": 0,
                "active_end_ts": 0,
                "next_event_id": nxt_id,
                "next_start_ts": nxt_ts,
                "announce_sent": False,
            })
            _save_state(state)
        return

    next_id = str(state.get("next_event_id") or "")
    next_start_ts = int(state.get("next_start_ts") or 0)
    announce_sent = bool(state.get("announce_sent"))
    ev = LIMITED_EVENTS.get(next_id)
    if not ev:
        nxt_id, nxt_ts = _schedule_next(now_ts)
        state.update({"next_event_id": nxt_id, "next_start_ts": nxt_ts, "announce_sent": False})
        _save_state(state)
        return

    # Старт
    if now_ts >= next_start_ts:
        duration_min = max(10, int(ev.get("duration_minutes") or 60))
        state.update({
            "active_event_id": next_id,
            "active_start_ts": now_ts,
            "active_end_ts": now_ts + duration_min * 60,
            "announce_sent": True,
        })
        _save_state(state)
        _broadcast(vk, str(ev.get("start") or f"⚡ Старт ивента «{ev.get('name', next_id)}»."))
        return

    # Анонс (только пока старт ещё не наступил)
    if not announce_sent and now_ts >= (next_start_ts - announce_before_min * 60):
        _broadcast(vk, str(ev.get("announce") or f"📢 Скоро начнётся ивент «{ev.get('name', next_id)}»."))
        state["announce_sent"] = True
        _save_state(state)


def get_active_limited_event() -> dict | None:
    """Текущий активный ограниченный ивент или None."""
    if not bool(getattr(config, "LIMITED_EVENTS_ENABLED", True)):
        return None
    state = _load_state(force=False)
    active_id = state.get("active_event_id")
    if not active_id:
        return None
    end_ts = int(state.get("active_end_ts") or 0)
    now_ts = _now_ts()
    if end_ts > 0 and now_ts >= end_ts:
        return None
    event = LIMITED_EVENTS.get(active_id)
    if not event:
        return None
    left_sec = max(0, end_ts - now_ts)
    return {
        "id": active_id,
        "name": str(event.get("name") or active_id),
        "seconds_left": left_sec,
        "mods": dict(event.get("mods") or {}),
    }


def get_limited_event_modifiers() -> dict:
    """Актуальные множители ограниченного ивента (или 1.0 по умолчанию)."""
    base = {
        "research_find_mult": 1.0,
        "research_danger_mult": 1.0,
        "artifact_event_mult": 1.0,
        "enemy_event_mult": 1.0,
        "enemy_stat_mult": 1.0,
        "combat_reward_mult": 1.0,
    }
    active = get_active_limited_event()
    if not active:
        return base
    mods = active.get("mods") or {}
    for k in tuple(base.keys()):
        try:
            base[k] = float(mods.get(k, 1.0) or 1.0)
        except Exception:
            base[k] = 1.0
    return base


def get_limited_events_catalog() -> list[dict]:
    """Список доступных ивентов для админки."""
    result = []
    for event_id, data in LIMITED_EVENTS.items():
        result.append({
            "id": event_id,
            "name": str(data.get("name") or event_id),
            "duration_minutes": int(data.get("duration_minutes") or 0),
        })
    return result


def get_limited_events_admin_status() -> dict:
    """Текущее состояние планировщика ограниченных ивентов."""
    state = _load_state(force=True)
    now_ts = _now_ts()
    out = {
        "now_ts": now_ts,
        "active_event_id": state.get("active_event_id"),
        "active_start_ts": int(state.get("active_start_ts") or 0),
        "active_end_ts": int(state.get("active_end_ts") or 0),
        "next_event_id": state.get("next_event_id"),
        "next_start_ts": int(state.get("next_start_ts") or 0),
        "announce_sent": bool(state.get("announce_sent")),
    }
    if out["active_event_id"]:
        out["active_seconds_left"] = max(0, out["active_end_ts"] - now_ts)
    else:
        out["active_seconds_left"] = 0
    out["next_seconds_left"] = max(0, out["next_start_ts"] - now_ts)
    return out


def force_start_limited_event(event_id: str, vk=None) -> dict:
    """Принудительно запустить ограниченный ивент (админ)."""
    event_id = str(event_id or "").strip().lower()
    event = LIMITED_EVENTS.get(event_id)
    if not event:
        return {"success": False, "message": f"Неизвестный ивент: {event_id}"}

    now_ts = _now_ts()
    state = _load_state(force=True)
    prev_active = state.get("active_event_id")
    if prev_active and vk is not None and prev_active in LIMITED_EVENTS:
        prev_name = LIMITED_EVENTS[prev_active].get("name", prev_active)
        _broadcast(vk, f"⚠️ Ивент «{prev_name}» остановлен администратором.")

    duration_min = max(10, int(event.get("duration_minutes") or 60))
    end_ts = now_ts + duration_min * 60
    nxt_id, nxt_ts = _schedule_next(end_ts)

    state.update({
        "active_event_id": event_id,
        "active_start_ts": now_ts,
        "active_end_ts": end_ts,
        "next_event_id": nxt_id,
        "next_start_ts": nxt_ts,
        "announce_sent": True,
    })
    _save_state(state)

    if vk is not None:
        _broadcast(
            vk,
            (
                f"⚡ АДМИН ЗАПУСТИЛ ИВЕНТ: «{event.get('name', event_id)}»\n\n"
                f"Длительность: {duration_min} мин."
            ),
        )

    return {
        "success": True,
        "event_id": event_id,
        "event_name": str(event.get("name") or event_id),
        "duration_minutes": duration_min,
        "ends_in_seconds": duration_min * 60,
    }


def force_stop_limited_event(vk=None) -> dict:
    """Принудительно остановить активный ограниченный ивент (админ)."""
    now_ts = _now_ts()
    state = _load_state(force=True)
    active_id = str(state.get("active_event_id") or "")
    if not active_id:
        return {"success": False, "message": "Сейчас нет активного ограниченного ивента."}

    active_name = str(LIMITED_EVENTS.get(active_id, {}).get("name") or active_id)
    nxt_id, nxt_ts = _schedule_next(now_ts)
    state.update({
        "active_event_id": None,
        "active_start_ts": 0,
        "active_end_ts": 0,
        "next_event_id": nxt_id,
        "next_start_ts": nxt_ts,
        "announce_sent": False,
    })
    _save_state(state)

    if vk is not None:
        _broadcast(vk, f"⛔ Ивент «{active_name}» досрочно остановлен администратором.")

    return {"success": True, "event_id": active_id, "event_name": active_name}
