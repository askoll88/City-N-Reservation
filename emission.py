"""
Система Выброса (Emission)
Глобальное событие, которое происходит 1-2 раза в сутки.
Предупреждение за 15 минут → урон игрокам в Зоне → бонусы после.
"""
import logging
import math
import random
import time
from datetime import datetime, timedelta, timezone

import config
import database
from constants import SAFE_LOCATIONS, DANGEROUS_LOCATIONS
from state_manager import (
    set_emission_pending, get_emission_pending, clear_emission_pending,
    has_pending_event, get_pending_event, clear_pending_event,
    is_in_dialog, get_dialog_info, clear_dialog_state,
    is_researching, get_research_data, clear_research_state,
    is_in_anomaly, get_anomaly_data, clear_anomaly_state,
    is_in_combat, clear_combat_state,
    has_travel_state, clear_travel_state, get_travel_data,
)
from handlers.keyboards import (
    create_emission_warning_keyboard,
    create_emission_impact_keyboard,
    create_location_keyboard,
    create_npc_dialog_keyboard,
    create_random_event_keyboard,
    create_travel_keyboard,
)

logger = logging.getLogger(__name__)

_EMISSION_RISK_LOCK_FLAG = "emission_risk_lock"
_EMISSION_RISK_EID_FLAG = "emission_risk_emission_id"
_EMISSION_IMPACT_RAD_SLOT_FLAG = "emission_impact_rad_slot"
_EMISSION_IMPACT_RAD_EID_FLAG = "emission_impact_rad_emission_id"

# Летальность выброса для неподготовленных вне укрытия.
EMISSION_FATAL_UNPREPARED_CHANCE = float(getattr(config, "EMISSION_FATAL_UNPREPARED_CHANCE", 0.07) or 0.07)
EMISSION_FATAL_RISK_MULT = float(getattr(config, "EMISSION_FATAL_RISK_MULT", 1.5) or 1.5)
EMISSION_PREPARED_HP_MIN = int(getattr(config, "EMISSION_PREPARED_HP_MIN", 65) or 65)
EMISSION_PREPARED_ENERGY_MIN = int(getattr(config, "EMISSION_PREPARED_ENERGY_MIN", 35) or 35)
EMISSION_PREPARED_MAX_RADIATION = int(getattr(config, "EMISSION_PREPARED_MAX_RADIATION", 90) or 90)
EMISSION_IMPACT_HALF_DEATH_RAD = int(getattr(config, "EMISSION_IMPACT_HALF_DEATH_RAD", 250) or 250)


def _log_emission_exception(
    action: str,
    *,
    emission_id: int | None = None,
    phase: str | None = None,
    user_id: int | None = None,
    location: str | None = None,
    extra: dict | None = None,
):
    """Единый формат логирования ошибок выброса с контекстом."""
    details = []
    if emission_id is not None:
        details.append(f"emission_id={emission_id}")
    if phase:
        details.append(f"phase={phase}")
    if user_id is not None:
        details.append(f"user_id={user_id}")
    if location:
        details.append(f"location={location}")
    if extra:
        details.append(f"extra={extra}")
    suffix = (" | " + ", ".join(details)) if details else ""
    logger.exception("Emission error: %s%s", action, suffix)


def _safe_vk_send(vk, *, action: str, emission_id: int | None = None, phase: str | None = None, ctx_user_id: int | None = None, location: str | None = None, **kwargs) -> bool:
    """Безопасная отправка VK-сообщения с обязательным логированием ошибок."""
    try:
        vk.messages.send(**kwargs)
        return True
    except Exception:
        _log_emission_exception(
            action,
            emission_id=emission_id,
            phase=phase,
            user_id=ctx_user_id,
            location=location,
            extra={"keys": sorted(list(kwargs.keys()))},
        )
        return False


# =========================================================================
# Фаза выброса
# =========================================================================

EMISSION_PHASE_PENDING = "pending"      # Выброс запланирован, ждём warning_time
EMISSION_PHASE_WARNING = "warning"      # Предупреждение отправлено (15 мин до удара)
EMISSION_PHASE_IMPACT = "impact"        # Выброс бьёт (30 мин)
EMISSION_PHASE_FINISHED = "finished"    # Завершён
EMISSION_PHASE_CANCELLED = "cancelled"  # Отменён
# После выброса: aftermath проверяется через get_emission_aftermath_active()
# (status = 'finished' + aftermath_end > NOW())


# =========================================================================
# Планирование выброса
# =========================================================================

def _to_naive_utc(dt: datetime) -> datetime:
    """Convert a timezone-aware datetime to naive UTC for consistent DB storage."""
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def schedule_next_emission():
    """
    Запланировать следующий выброс.
    Возвращает emission_id или None если не удалось.
    """
    if not config.EMISSION_ENABLED:
        return None

    existing = database.get_active_emission()
    if existing:
        logger.info(
            "schedule_next_emission: активный выброс уже есть (id=%s, status=%s), новый не создаю",
            existing.get("id"),
            existing.get("status"),
        )
        return existing.get("id")

    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC

    # Случайный интервал
    interval_hours = random.uniform(
        config.EMISSION_MIN_INTERVAL_HOURS,
        config.EMISSION_MAX_INTERVAL_HOURS,
    )

    warning_time = now + timedelta(hours=interval_hours)

    # Проверяем тихие часы — сдвигаем если нужно
    warning_time = _adjust_for_quiet_hours(warning_time)

    impact_time = warning_time + timedelta(minutes=config.EMISSION_WARNING_MINUTES)
    end_time = impact_time + timedelta(minutes=config.EMISSION_DURATION_MINUTES)
    aftermath_end = end_time + timedelta(minutes=config.EMISSION_AFTERMATH_MINUTES)

    emission_id = database.create_emission_schedule(
        warning_time=warning_time,
        impact_time=impact_time,
        end_time=end_time,
        aftermath_end=aftermath_end,
        emission_type='normal',
        admin_triggered=False,
    )

    logger.info(
        "Выброс запланирован: warning=%s, impact=%s, end=%s, aftermath=%s (id=%d)",
        warning_time.strftime("%H:%M:%S"),
        impact_time.strftime("%H:%M:%S"),
        end_time.strftime("%H:%M:%S"),
        aftermath_end.strftime("%H:%M:%S"),
        emission_id,
    )

    return emission_id


def schedule_admin_emission(vk):
    """Мгновенный выброс по команде админа (warning=now, impact=+15 мин)"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC
    warning_time = now
    impact_time = now + timedelta(minutes=config.EMISSION_WARNING_MINUTES)
    end_time = impact_time + timedelta(minutes=config.EMISSION_DURATION_MINUTES)
    aftermath_end = end_time + timedelta(minutes=config.EMISSION_AFTERMATH_MINUTES)

    logger.info(
        "schedule_admin_emission: now(UTC)=%s warning=%s impact=%s end=%s",
        now, warning_time, impact_time, end_time,
    )

    emission_id = database.create_emission_schedule(
        warning_time=warning_time,
        impact_time=impact_time,
        end_time=end_time,
        aftermath_end=aftermath_end,
        emission_type='normal',
        admin_triggered=True,
    )

    logger.info("Выброс запущен админом (id=%d)", emission_id)

    # Сразу отправляем предупреждение
    _send_warning_to_all_players(vk, emission_id)
    database.update_emission_status(emission_id, EMISSION_PHASE_WARNING)

    return emission_id


def _adjust_for_quiet_hours(dt: datetime) -> datetime:
    """
    Если время попадает в «тихие часы», сдвинуть до конца тихих часов.
    Тихие часы: EMISSION_QUIET_HOUR_START .. EMISSION_QUIET_HOUR_END (UTC)
    """
    start = config.EMISSION_QUIET_HOUR_START
    end = config.EMISSION_QUIET_HOUR_END

    if start < end:
        # Простой диапазон в пределах суток (напр. 2-7)
        if end > dt.hour >= start:
            dt = dt.replace(hour=end, minute=0, second=0, microsecond=0)
    else:
        # Пересекает полночь (напр. 22-6)
        if dt.hour >= start or dt.hour < end:
            # Сдвигаем на ближайший конец тихих часов
            if dt.hour >= start:
                dt = dt.replace(hour=end, minute=0, second=0, microsecond=0) + timedelta(days=1)
            else:
                dt = dt.replace(hour=end, minute=0, second=0, microsecond=0)

    return dt


# =========================================================================
# Цикл проверки (вызывается каждую минуту из scheduler thread)
# =========================================================================

def emission_tick(vk):
    """
    Проверить состояние выбросов и перейти к следующей фазе.
    Вызывается каждую минуту.
    """
    if not config.EMISSION_ENABLED:
        return

    # Перед обычным тиком выравниваем возможные рассинхроны статусов.
    # Это защищает от зависаний фаз после рестартов/пропущенных тиков.
    try:
        reconcile = database.reconcile_emission_statuses()
        reset_count = len(reconcile.get("reset_to_pending", []))
        finished_impacts = reconcile.get("finished_impacts", [])
        cancelled_count = len(reconcile.get("cancelled_warnings", [])) + len(reconcile.get("cancelled_pendings", []))

        if reset_count or finished_impacts or cancelled_count:
            logger.warning(
                "reconcile_emission_statuses: reset=%d, finished_impacts=%d, cancelled=%d",
                reset_count, len(finished_impacts), cancelled_count,
            )

        now_for_reconcile = datetime.now(timezone.utc).replace(tzinfo=None)
        for row in finished_impacts:
            eid = row["id"]
            aftermath_end = row.get("aftermath_end")
            if aftermath_end and getattr(aftermath_end, "tzinfo", None):
                aftermath_end = aftermath_end.replace(tzinfo=None)

            # Анонс aftermath только если окно последствий ещё актуально.
            if aftermath_end and now_for_reconcile < aftermath_end:
                _announce_aftermath(vk, eid)
                logger.info("Выброс #%d: reconcile -> FINISHED, aftermath объявлен", eid)
            else:
                logger.info("Выброс #%d: reconcile -> FINISHED, aftermath окно уже истекло", eid)

        if finished_impacts or cancelled_count:
            active_after_reconcile = database.get_active_emission()
            if not active_after_reconcile:
                next_id = schedule_next_emission()
                logger.info("reconcile: следующий выброс запланирован, id=%s", next_id)
    except Exception as e:
        logger.error("reconcile_emission_statuses: ошибка: %s", e, exc_info=True)

    emission = database.get_active_emission()
    if not emission:
        logger.warning("emission_tick: нет активных выбросов, планирую новый")
        try:
            next_id = schedule_next_emission()
            logger.info("emission_tick: автопланирование выполнено, id=%s", next_id)
        except Exception as e:
            logger.error("emission_tick: ошибка автопланирования: %s", e, exc_info=True)
        return

    # БД хранит TIMESTAMP (без tz) — делаем now тоже наивным для сравнения
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    emission_id = emission["id"]
    warning_time = emission["warning_time"]
    impact_time = emission["impact_time"]
    end_time = emission["end_time"]
    status = emission["status"]

    logger.info(
        "Выброс #%d: tick | status=%s | now=%s | warning=%s | impact=%s | end=%s | "
        "pending_chk=%s | warning_chk=%s | impact_chk=%s",
        emission_id, status, now, warning_time, impact_time, end_time,
        status == EMISSION_PHASE_PENDING and now >= warning_time,
        status == EMISSION_PHASE_WARNING and now >= impact_time,
        status == EMISSION_PHASE_IMPACT and now >= end_time,
    )

    # Переход: pending → warning
    if status == EMISSION_PHASE_PENDING and now >= warning_time:
        logger.info("Выброс #%d: переход в фазу WARNING (now=%s >= warning=%s)", emission_id, now, warning_time)
        try:
            _send_warning_to_all_players(vk, emission_id)
            database.update_emission_status(emission_id, EMISSION_PHASE_WARNING)
            logger.info("Выброс #%d: успешно перешёл в WARNING", emission_id)
        except Exception as e:
            logger.error("Выброс #%d: ОШИБКА при переходе в WARNING: %s", emission_id, e, exc_info=True)

    # Переход: warning → impact
    elif status == EMISSION_PHASE_WARNING and now >= impact_time:
        logger.info("Выброс #%d: переход в фазу IMPACT (now=%s >= impact=%s)", emission_id, now, impact_time)
        try:
            # Проверяем шанс отмены (как в S.T.A.L.K.E.R.)
            cancel_roll = random.random()
            logger.info("Выброс #%d: шанс отмены %.0f%%, rolled %.2f", emission_id, config.EMISSION_CANCEL_CHANCE * 100, cancel_roll)
            
            if cancel_roll < config.EMISSION_CANCEL_CHANCE:
                logger.info("Выброс #%d: ОТМЕНЁН (шанс %.0f%%)", emission_id, config.EMISSION_CANCEL_CHANCE * 100)
                _announce_emission_cancelled(vk, emission_id)
                database.update_emission_status(emission_id, EMISSION_PHASE_CANCELLED)
            else:
                logger.info("Выброс #%d: применяю урон", emission_id)
                _apply_emission_impact(vk, emission_id)
                database.update_emission_status(emission_id, EMISSION_PHASE_IMPACT)
                logger.info("Выброс #%d: успешно перешёл в IMPACT", emission_id)
        except Exception as e:
            logger.error("Выброс #%d: ОШИБКА при переходе в IMPACT: %s", emission_id, e, exc_info=True)

    # Фаза impact: продолжаем накапливать радиацию вне укрытий.
    elif status == EMISSION_PHASE_IMPACT and impact_time <= now < end_time:
        try:
            _apply_impact_radiation_accumulation(vk, emission)
        except Exception as e:
            logger.error("Выброс #%d: ошибка накопления радиации в impact: %s", emission_id, e, exc_info=True)

    # Переход: impact → finished (aftermath начинается автоматически)
    elif status == EMISSION_PHASE_IMPACT and now >= end_time:
        logger.info("Выброс #%d: переход в фазу FINISHED (now=%s >= end=%s)", emission_id, now, end_time)
        try:
            database.update_emission_status(emission_id, EMISSION_PHASE_FINISHED)
            _announce_aftermath(vk, emission_id)
            logger.info("Выброс #%d: успешно перешёл в FINISHED (aftermath активен)", emission_id)

            # Планируем следующий выброс
            next_id = schedule_next_emission()
            logger.info("Выброс #%d: следующий выброс запланирован, id=%s", emission_id, next_id)
        except Exception as e:
            logger.error("Выброс #%d: ОШИБКА при переходе в FINISHED: %s", emission_id, e, exc_info=True)
    else:
        logger.debug(
            "Выброс #%d: нет перехода | status=%s, now=%s | "
            "pending_check=%s, warning_check=%s, impact_check=%s",
            emission_id, status, now,
            status == EMISSION_PHASE_PENDING and now >= warning_time,
            status == EMISSION_PHASE_WARNING and now >= impact_time,
            status == EMISSION_PHASE_IMPACT and now >= end_time,
        )


# =========================================================================
# Фаза 1: Предупреждение (warning)
# =========================================================================

def _send_warning_to_all_players(vk, emission_id: int):
    """Отправить предупреждение всем игрокам в опасных зонах"""
    players = database.get_all_active_players()
    active = database.get_active_emission()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    lock_timer_text = "⏳ Блок безопасных мест для рискнувших через 10:00."
    if active and int(active.get("id") or 0) == int(emission_id):
        impact_time = active.get("impact_time")
        if impact_time:
            lock_time = impact_time - timedelta(minutes=5)
            lock_in_sec = max(0, int((lock_time - now).total_seconds()))
            m, s = divmod(lock_in_sec, 60)
            lock_timer_text = f"⏳ Блок безопасных мест для рискнувших через {m}:{s:02d}."

    warned_count = 0
    safe_count = 0

    for player in players:
        vk_id = player["vk_id"]
        location = player.get("location", "город")

        if location in SAFE_LOCATIONS:
            safe_count += 1
            # Игрок в безопасности — просто уведомляем
            _safe_vk_send(
                vk,
                action="send_warning_safe",
                emission_id=emission_id,
                phase=EMISSION_PHASE_WARNING,
                ctx_user_id=vk_id,
                location=location,
                user_id=vk_id,
                message=(
                    "⚠️ **ВНИМАНИЕ! ВЫБРОС!**\n\n"
                    "Зона предупреждает: через 15 минут начнётся Выброс!\n"
                    f"Ты в укрытии ({location}) — ты в безопасности.\n\n"
                    "🛡️ Укрытия: Город, Больница, Убежище\n\n"
                    f"{lock_timer_text}\n\n"
                    "Если ты в Зоне — срочно возвращайся в укрытие!"
                ),
                random_id=0,
            )
        else:
            warned_count += 1
            # Игрок в опасности — ставим pending событие
            emission_event = {
                "type": "emission_warning",
                "id": f"emission_warning_{emission_id}",
                "emission_id": emission_id,
                "phase": "warning",
                "location": location,
                "text": (
                    "⚠️ **ВНИМАНИЕ! ВЫБРОС!**\n\n"
                    "Сталкер, через 15 минут начнётся Выброс!\n"
                    f"Ты сейчас в: {location}\n\n"
                    "🚨 Срочно ищи укрытие!\n"
                    "🛡️ Укрытия: Город, Больница, Убежище\n\n"
                    f"{lock_timer_text}\n\n"
                    "Если не успеешь — Зона не будет щадить..."
                ),
                "choices": [
                    {
                        "label": "🏃 Бежать в укрытие",
                        "effect": {"flee_to_safe": True},
                    },
                    {
                        "label": "😰 Остаться и рискнуть",
                        "effect": {"stay_and_risk": True},
                    },
                ],
            }

            set_emission_pending(vk_id, emission_event)

            _safe_vk_send(
                vk,
                action="send_warning_danger",
                emission_id=emission_id,
                phase=EMISSION_PHASE_WARNING,
                ctx_user_id=vk_id,
                location=location,
                user_id=vk_id,
                message=emission_event["text"],
                keyboard=create_emission_warning_keyboard().get_keyboard(),
                random_id=0,
            )

    logger.info(
        "Выброс #%d: предупреждение отправлено. В опасности: %d, в безопасности: %d",
        emission_id, warned_count, safe_count,
    )


# =========================================================================
# Обработка ответа на предупреждение
# =========================================================================

def handle_emission_warning_response(player, vk, user_id: int, text: str) -> bool:
    """Обработать выбор игрока на предупреждение о выбросе"""
    event = get_emission_pending(user_id)
    if not event:
        return False

    try:
        # Handle both warning and impact phases
        phase = event.get("phase")
        if phase == "warning":
            return _handle_warning_choice(player, vk, user_id, event, text)
        if phase == "impact":
            return _handle_impact_choice(player, vk, user_id, event, text)
        return False
    except Exception:
        _log_emission_exception(
            "handle_emission_warning_response",
            emission_id=int(event.get("emission_id") or 0),
            phase=str(event.get("phase") or ""),
            user_id=user_id,
            location=getattr(player, "current_location_id", None),
            extra={"text": text[:64]},
        )
        return True


def _handle_warning_choice(player, vk, user_id: int, event: dict, text: str) -> bool:
    """Обработать выбор на фазе предупреждения"""
    text_lower = text.strip().lower()

    # Пропуск
    if text_lower in ("пропустить", "skip"):
        clear_emission_pending(user_id)
        _restore_interrupted_context(player, vk, user_id, "Ты остался в Зоне. Возвращаю к прерванному действию.")
        return True

    # Выбор
    choice_idx = None
    if text_lower.isdigit():
        choice_idx = int(text_lower) - 1
    else:
        for i, choice in enumerate(event.get("choices", [])):
            if choice["label"].lower() == text_lower:
                choice_idx = i
                break

    if choice_idx is None:
        vk.messages.send(
            user_id=user_id,
            message="Выбери: 'Бежать в укрытие' или 'Остаться и рискнуть'.",
            keyboard=create_emission_warning_keyboard().get_keyboard(),
            random_id=0,
        )
        return True

    choice = event["choices"][choice_idx]
    clear_emission_pending(user_id)

    if choice["effect"].get("flee_to_safe"):
        _abort_interrupted_context(user_id)
        database.set_user_flag(user_id, _EMISSION_RISK_LOCK_FLAG, 0)
        database.set_user_flag(user_id, _EMISSION_RISK_EID_FLAG, 0)
        return _flee_to_safe_location(player, vk, user_id)

    elif choice["effect"].get("stay_and_risk"):
        database.set_user_flag(user_id, _EMISSION_RISK_LOCK_FLAG, 1)
        database.set_user_flag(user_id, _EMISSION_RISK_EID_FLAG, int(event.get("emission_id") or 0))
        vk.messages.send(
            user_id=user_id,
            message=(
                "😰 Ты решил остаться в Зоне...\n\n"
                "Выброс не будет щадить. Готовься к последствиям.\n"
                "🩺 Попробуй восстановить HP перед ударом!\n\n"
                "⚠️ Важно: за 5 минут до удара путь в безопасные места будет закрыт."
            ),
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        _restore_interrupted_context(player, vk, user_id, "Ты остался в Зоне. Прерванный сценарий продолжен.")

    return True


def _handle_impact_choice(player, vk, user_id: int, event: dict, text: str) -> bool:
    """Обработать выбор на фазе удара (impact)"""
    text_lower = text.strip().lower()

    if text_lower in ("пропустить", "skip"):
        clear_emission_pending(user_id)
        _restore_interrupted_context(player, vk, user_id, "Выброс бушует. Продолжаем прерванное действие.")
        return True

    # "Бежать в укрытие" during impact
    if "бежать" in text_lower or "укрытие" in text_lower:
        blocked, _ = is_emission_safe_entry_blocked_for_user(user_id)
        if blocked:
            clear_emission_pending(user_id)
            vk.messages.send(
                user_id=user_id,
                message=(
                    "☢️ Слишком поздно.\n"
                    "Ты выбрал риск и путь в безопасные зоны уже закрыт до конца выброса."
                ),
                keyboard=create_emission_impact_keyboard(player.current_location_id).get_keyboard(),
                random_id=0,
            )
            return True
        _abort_interrupted_context(user_id)
        clear_emission_pending(user_id)
        return _flee_to_safe_location(player, vk, user_id)

    # "Лечиться" during impact
    if "леч" in text_lower:
        clear_emission_pending(user_id)
        vk.messages.send(
            user_id=user_id,
            message=(
                "🩺 Ты пытаешься лечиться...\n\n"
                "Выброс мешает — напиши 'больница' или используй аптечку."
            ),
            keyboard=create_emission_impact_keyboard(player.current_location_id).get_keyboard(),
            random_id=0,
        )
        return True

    # "Инвентарь"
    if "инвентар" in text_lower:
        from handlers.commands import handle_inventory_command
        handle_inventory_command(player, vk, user_id)
        return True

    vk.messages.send(
        user_id=user_id,
        message="Во время выброса доступны: 'Бежать в укрытие', 'Лечиться' или 'Инвентарь'.",
        keyboard=create_emission_impact_keyboard(player.current_location_id).get_keyboard(),
        random_id=0,
    )
    return True


def _abort_interrupted_context(user_id: int):
    """Автостоп прерванных сценариев, если игрок убежал в safe."""
    clear_pending_event(user_id)
    clear_dialog_state(user_id)
    clear_research_state(user_id)
    clear_anomaly_state(user_id)
    clear_combat_state(user_id)
    clear_travel_state(user_id)


def _restore_interrupted_context(player, vk, user_id: int, header: str = ""):
    """
    Восстановить интерфейс прерванного сценария после ответа на выброс.
    Приоритет: бой -> аномалия -> квест/рандом-ивент -> диалог -> исследование -> путь.
    """
    from random_events import format_event_message
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
    from handlers.combat import create_combat_keyboard

    if is_in_combat(user_id):
        msg = "⚔️ Бой продолжается."
        if header:
            msg = f"{header}\n\n{msg}"
        vk.messages.send(
            user_id=user_id,
            message=msg,
            keyboard=create_combat_keyboard(player, user_id).get_keyboard(),
            random_id=0,
        )
        return

    if is_in_anomaly(user_id):
        anomaly = get_anomaly_data(user_id) or {}
        anomaly_name = anomaly.get("anomaly_name", "аномалия")
        shells = database.get_user_shells(user_id)
        keyboard = VkKeyboard(one_time=False)
        keyboard.add_button("Обойти", color=VkKeyboardColor.POSITIVE)
        if shells > 0:
            keyboard.add_button("Бросить гильзу", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("Отступить", color=VkKeyboardColor.NEGATIVE)
        msg = f"⚠️ Ты всё ещё в аномалии: {anomaly_name}.\nВыбери действие."
        if header:
            msg = f"{header}\n\n{msg}"
        vk.messages.send(user_id=user_id, message=msg, keyboard=keyboard.get_keyboard(), random_id=0)
        return

    if has_pending_event(user_id):
        event = get_pending_event(user_id)
        if event:
            stage = int(event.get("_stage_index", 0) or 0)
            msg = format_event_message(event, stage)
            if header:
                msg = f"{header}\n\n{msg}"
            vk.messages.send(
                user_id=user_id,
                message=msg,
                keyboard=create_random_event_keyboard(event, stage_index=stage).get_keyboard(),
                random_id=0,
            )
            return

    if is_in_dialog(user_id):
        dialog = get_dialog_info(user_id) or {}
        npc_id = dialog.get("npc")
        msg = "💬 Диалог продолжается."
        if header:
            msg = f"{header}\n\n{msg}"
        if npc_id:
            vk.messages.send(
                user_id=user_id,
                message=msg,
                keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
                random_id=0,
            )
            return

    if is_researching(user_id):
        data = get_research_data(user_id) or {}
        remaining = int(max(0, data.get("duration", 0) - (time.time() - data.get("start_time", 0))))
        msg = (
            "⏳ Исследование продолжается.\n\n"
            f"Осталось: {remaining} сек.\n"
            "Можно ждать результат или написать 'отмена'."
        )
        if header:
            msg = f"{header}\n\n{msg}"
        vk.messages.send(user_id=user_id, message=msg, random_id=0)
        return

    if has_travel_state(user_id):
        travel = get_travel_data(user_id) or {}
        frm = travel.get("from_location", "?")
        to = travel.get("to_location", "?")
        msg = f"🧭 Путь продолжается: {frm} → {to}"
        if header:
            msg = f"{header}\n\n{msg}"
        vk.messages.send(
            user_id=user_id,
            message=msg,
            keyboard=create_travel_keyboard().get_keyboard(),
            random_id=0,
        )
        return

    if header:
        vk.messages.send(
            user_id=user_id,
            message=header,
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )


def _flee_to_safe_location(player, vk, user_id: int) -> bool:
    """Переместить игрока в случайное безопасное место"""
    import random
    safe_location = random.choice(SAFE_LOCATIONS)

    player.current_location_id = safe_location
    player.energy = max(0, player.energy - 10)  # Затраты энергии на бегство
    database.set_user_flag(user_id, _EMISSION_RISK_LOCK_FLAG, 0)
    database.set_user_flag(user_id, _EMISSION_RISK_EID_FLAG, 0)
    database.set_user_flag(user_id, _EMISSION_IMPACT_RAD_SLOT_FLAG, -1)
    database.set_user_flag(user_id, _EMISSION_IMPACT_RAD_EID_FLAG, 0)

    database.update_user_stats(
        user_id,
        location=safe_location,
        energy=player.energy,
    )

    vk.messages.send(
        user_id=user_id,
        message=(
            f"🏃 Ты бежал в укрытие — {safe_location}!\n\n"
            "Выброс бушует, но ты в безопасности.\n"
            f"⚡ Энергия: -10 (быстрый переход)\n"
            f"⚡ Текущая энергия: {player.energy}"
        ),
        keyboard=create_location_keyboard(safe_location, player.level).get_keyboard(),
        random_id=0,
    )
    return True


# =========================================================================
# Фаза 2: Удар (impact)
# =========================================================================

def _apply_emission_impact(vk, emission_id: int):
    """Применить урон всем игрокам, которые всё ещё в опасных зонах"""
    players = database.get_all_active_players()

    damaged = 0
    safe = 0
    died = 0
    failed = 0

    for player_data in players:
        try:
            vk_id = player_data["vk_id"]
            location = player_data.get("location", "город")
            user_row = database.get_user_by_vk(vk_id) or {}
            current_health = int(user_row.get("health") or player_data.get("health") or 100)

            if location in SAFE_LOCATIONS:
                safe += 1
                _safe_vk_send(
                    vk,
                    action="send_impact_safe",
                    emission_id=emission_id,
                    phase=EMISSION_PHASE_IMPACT,
                    ctx_user_id=vk_id,
                    location=location,
                    user_id=vk_id,
                    message=(
                        "☢️ **ВЫБРОС НАЧАЛСЯ!**\n\n"
                        f"Ты в укрытии ({location}) — урон не получен.\n"
                        "Оставайся в безопасности до окончания выброса."
                    ),
                    random_id=0,
                )
                continue

            # --- УРОН ---
            damage_pct = random.uniform(
                config.EMISSION_DAMAGE_PCT_MIN,
                config.EMISSION_DAMAGE_PCT_MAX,
            )
            damage = int(current_health * damage_pct)
            new_health = max(1, current_health - damage)

            # Радиация
            radiation = config.EMISSION_RADIATION + random.randint(-5, 10)
            new_radiation = int(user_row.get("radiation") or 0) + radiation

            # Урон от накопленной радиации: чем выше накопление, тем быстрее тает HP.
            from player import calculate_radiation_hp_loss, format_radiation_rate, get_radiation_stage
            rad_overload_damage = calculate_radiation_hp_loss(new_radiation, new_health)
            new_health = max(1, new_health - rad_overload_damage)

            # Небольшой шанс погибнуть от выброса, если игрок в зоне и не готов.
            prepared, prep_state = _is_player_prepared_for_emission(vk_id, user_row)
            risk_locked = bool(int(database.get_user_flag(vk_id, _EMISSION_RISK_LOCK_FLAG, 0) or 0))
            fatal_hit, fatal_roll, fatal_chance = _roll_unprepared_fatality(prepared, risk_locked)
            if fatal_hit:
                death_result = _apply_emission_death_penalty(vk_id, user_row)

                database.record_emission_damage(
                    vk_id=vk_id,
                    emission_id=emission_id,
                    damage=max(1, current_health),
                    radiation=radiation,
                    items_lost=0,
                    was_safe=False,
                )
                clear_emission_pending(vk_id)
                damaged += 1
                died += 1

                prep_line = "Неподготовлен: " + ", ".join(prep_state.get("missing", []))
                risk_line = "Да" if risk_locked else "Нет"
                _safe_vk_send(
                    vk,
                    action="send_impact_fatal",
                    emission_id=emission_id,
                    phase=EMISSION_PHASE_IMPACT,
                    ctx_user_id=vk_id,
                    location=location,
                    user_id=vk_id,
                    message=(
                        "☢️ **ВЫБРОС НАЧАЛСЯ!**\n\n"
                        "Ты не успел укрыться, а Зона не прощает ошибок.\n"
                        "💀 Смертельная волна выброса накрыла тебя.\n\n"
                        f"🎲 Шанс фатального исхода: {fatal_chance * 100:.1f}% (бросок {fatal_roll * 100:.1f}%)\n"
                        f"⚠️ Риск-режим: {risk_line}\n"
                        f"📉 {prep_line}\n\n"
                        f"Штраф: -{death_result['money_lost']} руб, -{death_result['experience_lost']} XP.\n"
                        "Ты очнулся в больнице."
                    ),
                    keyboard=create_location_keyboard("больница", user_row.get("level")).get_keyboard(),
                    random_id=0,
                )
                continue

            # Потеря предметов
            items_lost = 0
            lost_items_msg = ""
            if random.random() < config.EMISSION_ITEM_LOSS_CHANCE:
                items_lost = random.randint(1, config.EMISSION_ITEM_LOSS_MAX)
                # Удаляем случайные предметы (не экипировку)
                lost_items_msg = _remove_random_items(vk_id, items_lost)

            # Сохраняем
            database.update_user_stats(
                vk_id,
                health=new_health,
                radiation=new_radiation,
            )

            # Логируем
            database.record_emission_damage(
                vk_id=vk_id,
                emission_id=emission_id,
                damage=damage,
                radiation=radiation,
                items_lost=items_lost,
                was_safe=False,
            )

            damaged += 1
            if new_health <= 1:
                died += 1

            # Ставим pending событие для возможности убежать
            items_line = ""
            if lost_items_msg:
                items_line = f"📦 Потеряны предметы: {lost_items_msg}\n"
            death_line = ""
            if new_health <= 1:
                death_line = "💀 Ты на грани смерти! Срочно лечись!\n\n"
            stage = get_radiation_stage(new_radiation)

            impact_event = {
                "type": "emission_impact",
                "id": f"emission_impact_{emission_id}",
                "emission_id": emission_id,
                "phase": "impact",
                "location": location,
                "text": (
                    f"☢️ **ВЫБРОС НАЧАЛСЯ!**\n\n"
                    f"Ты был в: {location}\n"
                    f"💔 Получено урона: -{damage} HP ({current_health} → {new_health})\n"
                    f"☢️ Радиация: +{radiation}\n"
                    f"☢️ Уровень: {new_radiation} ед. ({format_radiation_rate(new_radiation)})\n"
                    f"🧪 Стадия: {stage['name']}\n"
                    f"☣️ Токсичность: -{rad_overload_damage} HP (накопление)\n"
                    f"{items_line}"
                    f"{death_line}"
                    "Что делать?"
                ),
                "choices": [
                    {
                        "label": "🏃 Бежать в укрытие",
                        "effect": {"flee_to_safe": True},
                    },
                ],
            }
            set_emission_pending(vk_id, impact_event)

            # Отправляем результат игроку
            _safe_vk_send(
                vk,
                action="send_impact_damage",
                emission_id=emission_id,
                phase=EMISSION_PHASE_IMPACT,
                ctx_user_id=vk_id,
                location=location,
                user_id=vk_id,
                message=impact_event["text"],
                keyboard=create_emission_impact_keyboard(location).get_keyboard(),
                random_id=0,
            )
        except Exception as e:
            failed += 1
            _log_emission_exception(
                "apply_emission_impact_player",
                emission_id=emission_id,
                phase=EMISSION_PHASE_IMPACT,
                user_id=player_data.get("vk_id"),
                location=player_data.get("location"),
                extra={"error": str(e)},
            )

    logger.info(
        "Выброс #%d: удар применён. Повреждено: %d, погибло: %d, в безопасности: %d, ошибок: %d",
        emission_id, damaged, died, safe, failed,
    )


def _impact_radiation_gain_per_minute(impact_time: datetime, end_time: datetime) -> int:
    """Прирост рад/мин: к половине окна impact набегает ~уровень почти-верной смерти."""
    duration_sec = max(60, int((end_time - impact_time).total_seconds()))
    half_minutes = max(1, (duration_sec // 2) // 60)
    return max(8, int(math.ceil(EMISSION_IMPACT_HALF_DEATH_RAD / half_minutes)))


def _apply_impact_radiation_accumulation(vk, emission: dict):
    """
    Во время impact радиация продолжает расти каждую минуту у игроков вне safe.
    Без антирада игрок быстро выходит в критическую зону.
    """
    emission_id = int(emission.get("id") or 0)
    impact_time = emission.get("impact_time")
    end_time = emission.get("end_time")
    if not impact_time or not end_time:
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if now < impact_time or now >= end_time:
        return

    minute_slot = int((now - impact_time).total_seconds() // 60)
    per_min_gain = _impact_radiation_gain_per_minute(impact_time, end_time)
    players = database.get_all_active_players()
    from player import calculate_radiation_hp_loss, format_radiation_rate

    for player_data in players:
        try:
            vk_id = int(player_data["vk_id"])
            location = player_data.get("location", "город")
            if location in SAFE_LOCATIONS:
                continue

            last_eid = int(database.get_user_flag(vk_id, _EMISSION_IMPACT_RAD_EID_FLAG, 0) or 0)
            last_slot = int(database.get_user_flag(vk_id, _EMISSION_IMPACT_RAD_SLOT_FLAG, -1) or -1)
            if last_eid == emission_id and last_slot == minute_slot:
                continue

            database.set_user_flag(vk_id, _EMISSION_IMPACT_RAD_EID_FLAG, emission_id)
            database.set_user_flag(vk_id, _EMISSION_IMPACT_RAD_SLOT_FLAG, minute_slot)

            user = database.get_user_by_vk(vk_id) or {}
            hp = int(user.get("health") or 1)
            rad = int(user.get("radiation") or 0)

            risk_locked = bool(int(database.get_user_flag(vk_id, _EMISSION_RISK_LOCK_FLAG, 0) or 0))
            risk_mult = 1.2 if risk_locked else 1.0
            rad_gain = max(1, int((per_min_gain + random.randint(-2, 3)) * risk_mult))
            new_radiation = rad + rad_gain
            overload = calculate_radiation_hp_loss(new_radiation, hp)
            new_health = max(1, hp - overload)

            # При критическом накоплении больше не держим игрока "вечно на 1 HP":
            # выброс добивает и отправляет в больницу.
            if new_health <= 1 and new_radiation >= EMISSION_IMPACT_HALF_DEATH_RAD:
                death_result = _apply_emission_death_penalty(vk_id, user)
                clear_emission_pending(vk_id)
                _safe_vk_send(
                    vk,
                    action="send_impact_critical_radiation_death",
                    emission_id=emission_id,
                    phase=EMISSION_PHASE_IMPACT,
                    ctx_user_id=vk_id,
                    location=location,
                    user_id=vk_id,
                    message=(
                        "☣️ **Критическое облучение**\n\n"
                        f"☢️ Радиация достигла {new_radiation} ед. ({format_radiation_rate(new_radiation)}).\n"
                        "Организм не выдержал продолжающийся выброс.\n\n"
                        f"Штраф: -{death_result['money_lost']} руб, -{death_result['experience_lost']} XP.\n"
                        "Ты очнулся в больнице."
                    ),
                    keyboard=create_location_keyboard("больница", user.get("level")).get_keyboard(),
                    random_id=0,
                )
                continue

            database.update_user_stats(vk_id, health=new_health, radiation=new_radiation)

            # Сообщения редко: каждые 5 минут и при критических порогах.
            if (minute_slot % 5 == 0) or new_radiation >= 220 or new_health <= 15:
                escape_hint = (
                    "Путь в укрытие уже закрыт до конца выброса."
                    if risk_locked else
                    "Можно попытаться прорваться в укрытие."
                )
                _safe_vk_send(
                    vk,
                    action="send_impact_radiation_tick",
                    emission_id=emission_id,
                    phase=EMISSION_PHASE_IMPACT,
                    ctx_user_id=vk_id,
                    location=location,
                    user_id=vk_id,
                    message=(
                        "☣️ **Выброс усиливается**\n\n"
                        f"☢️ Радиация: +{rad_gain} (итого {new_radiation} ед., {format_radiation_rate(new_radiation)})\n"
                        f"💔 Урон от токсичности: -{overload} HP (осталось {new_health})\n\n"
                        f"Спастись поможет антирад. {escape_hint}"
                    ),
                    keyboard=create_emission_impact_keyboard(location).get_keyboard(),
                    random_id=0,
                )
        except Exception as e:
            _log_emission_exception(
                "impact_radiation_accumulation_player",
                emission_id=emission_id,
                phase=EMISSION_PHASE_IMPACT,
                user_id=player_data.get("vk_id"),
                location=player_data.get("location"),
                extra={"error": str(e), "minute_slot": minute_slot},
            )


def _is_player_prepared_for_emission(vk_id: int, user_row: dict) -> tuple[bool, dict]:
    """Определить, подготовлен ли игрок к выбросу."""
    hp = int(user_row.get("health") or 0)
    energy = int(user_row.get("energy") or 0)
    radiation = int(user_row.get("radiation") or 0)

    inv = database.get_user_inventory(vk_id)
    supply_tokens = (
        "аптечк", "бинт", "антирад", "анти-рад", "анти рад",
        "водк", "энергетик", "стим",
    )
    has_supplies = any(
        int(item.get("quantity") or 0) > 0 and any(tok in str(item.get("name", "")).lower() for tok in supply_tokens)
        for item in inv
    )

    checks = {
        "hp": hp >= EMISSION_PREPARED_HP_MIN,
        "energy": energy >= EMISSION_PREPARED_ENERGY_MIN,
        "radiation": radiation <= EMISSION_PREPARED_MAX_RADIATION,
        "supplies": has_supplies,
    }
    score = sum(1 for ok in checks.values() if ok)

    missing = []
    if not checks["hp"]:
        missing.append(f"HP<{EMISSION_PREPARED_HP_MIN}")
    if not checks["energy"]:
        missing.append(f"Энергия<{EMISSION_PREPARED_ENERGY_MIN}")
    if not checks["radiation"]:
        missing.append(f"Радиация>{EMISSION_PREPARED_MAX_RADIATION}")
    if not checks["supplies"]:
        missing.append("нет расходников")

    # Считаем игрока готовым, если выполняются хотя бы 3 условия из 4.
    return score >= 3, {"score": score, "checks": checks, "missing": missing}


def _roll_unprepared_fatality(prepared: bool, risk_locked: bool) -> tuple[bool, float, float]:
    """Ролл мгновенной смерти для неподготовленных игроков вне укрытия."""
    if prepared:
        return False, 1.0, 0.0
    chance = EMISSION_FATAL_UNPREPARED_CHANCE
    if risk_locked:
        chance *= EMISSION_FATAL_RISK_MULT
    chance = max(0.0, min(0.35, float(chance)))
    roll = random.random()
    return roll < chance, roll, chance


def _apply_emission_death_penalty(vk_id: int, user_row: dict) -> dict:
    """Применить штрафы смерти от выброса и вернуть игрока в больницу."""
    from state_manager import (
        clear_travel_state, clear_combat_state, clear_dialog_state,
        clear_research_state, clear_anomaly_state,
    )
    from player import Player

    level = int(user_row.get("level") or 1)
    old_money = int(user_row.get("money") or 0)
    old_experience = int(user_row.get("experience") or 0)

    money_lost = int(old_money * 0.1)
    new_money = max(0, old_money - money_lost)

    exp_loss = int(old_experience * 0.25)
    min_exp = int(Player.LEVELS.get(level, 0))
    new_experience = max(min_exp, old_experience - exp_loss)
    experience_lost = old_experience - new_experience

    clear_travel_state(vk_id)
    clear_combat_state(vk_id)
    clear_dialog_state(vk_id)
    clear_research_state(vk_id)
    clear_anomaly_state(vk_id)

    database.update_user_stats(
        vk_id,
        health=50,
        energy=50,
        radiation=0,
        money=new_money,
        experience=new_experience,
        location="больница",
    )
    database.set_user_flag(vk_id, _EMISSION_RISK_LOCK_FLAG, 0)
    database.set_user_flag(vk_id, _EMISSION_RISK_EID_FLAG, 0)
    database.set_user_flag(vk_id, _EMISSION_IMPACT_RAD_SLOT_FLAG, -1)
    database.set_user_flag(vk_id, _EMISSION_IMPACT_RAD_EID_FLAG, 0)

    return {
        "money_lost": money_lost,
        "experience_lost": experience_lost,
        "new_money": new_money,
        "new_experience": new_experience,
    }


def _remove_random_items(vk_id: int, count: int) -> str:
    """Удалить случайные предметы из инвентаря. Возвращает список потерянных."""
    inventory = database.get_user_inventory(vk_id)
    if not inventory:
        return ""

    # Исключаем ключевые предметы
    protected = {"Гильза"}
    removable = [item for item in inventory if item["name"] not in protected]

    if not removable:
        return ""

    lost = []
    for _ in range(min(count, len(removable))):
        item = random.choice(removable)
        removable.remove(item)
        qty = item.get("quantity", 1)
        database.remove_item_from_inventory(vk_id, item["name"], qty)
        lost.append(f"{item['name']} x{qty}")

    return ", ".join(lost) if lost else ""


# =========================================================================
# Фаза 3: Последствия (aftermath)
# =========================================================================

def _announce_emission_cancelled(vk, emission_id: int):
    """Объявить об отмене выброса — Зона передумала"""
    cancel_messages = [
        (
            "📻 **ВНИМАНИЕ! Выброс отменён!**\n\n"
            "Приборы затихли. Зона... передумала.\n"
            "Аномальная активность пошла на спад.\n\n"
            "Сталкеры, выдыхайте. Но Зона не прощает беспечность — "
            "она может передумать снова."
        ),
        (
            "📻 **Отбой тревоги! Выброс отменён!**\n\n"
            "Детекторы показывают спад. Выброс растворился\n"
            "так же внезапно, как и начался.\n\n"
            "Удача улыбнулась тебе, сталкер.\n"
            "Но в Зоне удаче не доверяют..."
        ),
        (
            "📻 **Выброс отменён!**\n\n"
            "Неизвестные причины. Зона аномально спокойна.\n"
            "Может, кто-то наверху решил за нас?\n\n"
            "Продолжай работу, сталкер.\n"
            "Но будь готов — следующий может не отмениться."
        ),
    ]

    players = database.get_all_active_players()

    for player_data in players:
        vk_id = player_data["vk_id"]
        # Очищаем pending событие выброса
        clear_emission_pending(vk_id)
        database.set_user_flag(vk_id, _EMISSION_RISK_LOCK_FLAG, 0)
        database.set_user_flag(vk_id, _EMISSION_RISK_EID_FLAG, 0)
        database.set_user_flag(vk_id, _EMISSION_IMPACT_RAD_SLOT_FLAG, -1)
        database.set_user_flag(vk_id, _EMISSION_IMPACT_RAD_EID_FLAG, 0)

        try:
            vk.messages.send(
                user_id=vk_id,
                message=random.choice(cancel_messages),
                random_id=0,
            )
        except Exception:
            _log_emission_exception(
                "announce_cancelled_send",
                emission_id=emission_id,
                phase=EMISSION_PHASE_CANCELLED,
                user_id=vk_id,
            )

    logger.info("Выброс #%d: отменён, сообщения отправлены", emission_id)


def _announce_aftermath(vk, emission_id: int):
    """Объявить о фазе последствий — бонусы для всех"""
    players = database.get_all_active_players()

    for player_data in players:
        vk_id = player_data["vk_id"]
        database.set_user_flag(vk_id, _EMISSION_RISK_LOCK_FLAG, 0)
        database.set_user_flag(vk_id, _EMISSION_RISK_EID_FLAG, 0)
        database.set_user_flag(vk_id, _EMISSION_IMPACT_RAD_SLOT_FLAG, -1)
        database.set_user_flag(vk_id, _EMISSION_IMPACT_RAD_EID_FLAG, 0)
        try:
            vk.messages.send(
                user_id=vk_id,
                message=(
                    "🌅 **Выброс завершился!**\n\n"
                    "Зона успокоилась. В оставшихся аномалиях\n"
                    "появились редкие артефакты!\n\n"
                    "🔥 Бонусы (1 час):\n"
                    "• +50% шанс найти артефакты\n"
                    "• Могут появиться редкие мутанты\n"
                    "• Новые тайники на дорогах\n\n"
                    "Не упусти момент, сталкер!"
                ),
                random_id=0,
            )
        except Exception:
            _log_emission_exception(
                "announce_aftermath_send",
                emission_id=emission_id,
                phase=EMISSION_PHASE_FINISHED,
                user_id=vk_id,
            )

    logger.info("Выброс #%d: объявлены последствия (бонусы)", emission_id)


# =========================================================================
# Проверка бонуса артефактов
# =========================================================================

def is_emission_aftermath_active() -> bool:
    """Проверить, активна ли фаза последствий (бонусы артефактов)"""
    aftermath = database.get_emission_aftermath_active()
    return aftermath is not None


def get_emission_artifact_bonus() -> float:
    """Получить бонус к шансу артефактов (1.0 = без бонуса)"""
    if is_emission_aftermath_active():
        return 1.0 + config.EMISSION_BONUS_ARTIFACT_CHANCE
    return 1.0


def is_emission_rare_enemy_bonus() -> bool:
    """Проверить, активен ли бонус редких врагов"""
    if not is_emission_aftermath_active():
        return False
    return random.random() < config.EMISSION_BONUS_RARE_ENEMY_CHANCE


def is_emission_safe_entry_blocked_for_user(user_id: int) -> tuple[bool, int]:
    """
    Блок входа в безопасные локации для игроков, выбравших риск.
    Возвращает (blocked, seconds_to_impact).
    """
    lock_flag = int(database.get_user_flag(user_id, _EMISSION_RISK_LOCK_FLAG, 0) or 0)
    if lock_flag != 1:
        return False, 0

    emission = database.get_active_emission()
    if not emission:
        return False, 0

    emission_id = int(emission.get("id") or 0)
    locked_eid = int(database.get_user_flag(user_id, _EMISSION_RISK_EID_FLAG, 0) or 0)
    if locked_eid and locked_eid != emission_id:
        return False, 0

    status = emission.get("status")
    impact_time = emission.get("impact_time")
    end_time = emission.get("end_time")
    if not impact_time or not end_time:
        return False, 0

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    lock_start = impact_time - timedelta(minutes=5)
    seconds_to_impact = max(0, int((impact_time - now).total_seconds()))

    if status == EMISSION_PHASE_WARNING and lock_start <= now <= end_time:
        return True, seconds_to_impact
    if status == EMISSION_PHASE_IMPACT and now <= end_time:
        return True, seconds_to_impact

    return False, seconds_to_impact


def mark_emission_safe_exit_during_impact(user_id: int, from_location: str, to_location: str) -> bool:
    """
    Если игрок вышел из safe-локации в impact, блокируем возврат в safe до конца impact.
    """
    if from_location not in SAFE_LOCATIONS or to_location in SAFE_LOCATIONS:
        return False

    emission = database.get_active_emission()
    if not emission:
        return False
    if emission.get("status") != EMISSION_PHASE_IMPACT:
        return False

    impact_time = emission.get("impact_time")
    end_time = emission.get("end_time")
    if not impact_time or not end_time:
        return False

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not (impact_time <= now <= end_time):
        return False

    database.set_user_flag(user_id, _EMISSION_RISK_LOCK_FLAG, 1)
    database.set_user_flag(user_id, _EMISSION_RISK_EID_FLAG, int(emission.get("id") or 0))
    return True


# =========================================================================
# Проверка выброса при действии игрока
# =========================================================================

def check_emission_during_action(vk, user_id: int, location: str) -> bool:
    """
    Проверить, идёт ли выброс прямо сейчас.
    Если да и игрок в опасной зоне — применить урон.
    Возвращает True если выброс был применён.
    """
    emission = database.get_active_emission()
    if not emission:
        return False

    # БД хранит TIMESTAMP (без tz) — делаем now тоже наивным
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    impact_time = emission["impact_time"]
    end_time = emission["end_time"]

    # Только в фазе impact
    if emission["status"] != EMISSION_PHASE_IMPACT:
        return False

    if now < impact_time or now > end_time:
        return False

    if location in SAFE_LOCATIONS:
        return False

    # Применяем урон
    from player import Player
    player = Player(user_id)

    damage_pct = random.uniform(
        config.EMISSION_DAMAGE_PCT_MIN,
        config.EMISSION_DAMAGE_PCT_MAX,
    )
    damage = int(player.health * damage_pct)
    player.health = max(1, player.health - damage)
    player.radiation = player.radiation + config.EMISSION_RADIATION

    from player import calculate_radiation_hp_loss, format_radiation_rate, get_radiation_stage
    rad_overload_damage = calculate_radiation_hp_loss(player.radiation, player.health)
    player.health = max(1, player.health - rad_overload_damage)

    database.update_user_stats(
        user_id,
        health=player.health,
        radiation=player.radiation,
    )

    stage = get_radiation_stage(player.radiation)
    try:
        vk.messages.send(
            user_id=user_id,
            message=(
                f"☢️ **ВЫБРОС БУШУЕТ!**\n\n"
                f"Ты в Зоне ({location}) и получаешь урон!\n"
                f"💔 Урон: -{damage} HP\n"
                f"☣️ Токсичность: -{rad_overload_damage} HP\n"
                f"❤️ HP: {player.health}\n"
                f"☢️ Радиация: {player.radiation} ед. ({format_radiation_rate(player.radiation)})\n"
                f"🧪 Стадия: {stage['name']}\n\n"
                "Беги в укрытие!"
            ),
            random_id=0,
        )
    except Exception:
        _log_emission_exception(
            "check_emission_during_action_send",
            emission_id=int(emission.get("id") or 0),
            phase=EMISSION_PHASE_IMPACT,
            user_id=user_id,
            location=location,
        )

    return True
