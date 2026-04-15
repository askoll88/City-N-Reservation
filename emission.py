"""
Система Выброса (Emission)
Глобальное событие, которое происходит 1-2 раза в сутки.
Предупреждение за 15 минут → урон игрокам в Зоне → бонусы после.
"""
import logging
import random
import time
from datetime import datetime, timedelta, timezone

import config
import database
from constants import SAFE_LOCATIONS, DANGEROUS_LOCATIONS
from state_manager import (
    set_emission_pending, get_emission_pending, clear_emission_pending,
)
from handlers.keyboards import (
    create_emission_warning_keyboard,
    create_emission_impact_keyboard,
    create_location_keyboard,
)

logger = logging.getLogger(__name__)


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

    emission = database.get_active_emission()
    if not emission:
        logger.debug("emission_tick: нет активных выбросов")
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

    warned_count = 0
    safe_count = 0

    for player in players:
        vk_id = player["vk_id"]
        location = player.get("location", "город")

        if location in SAFE_LOCATIONS:
            safe_count += 1
            # Игрок в безопасности — просто уведомляем
            try:
                vk.messages.send(
                    user_id=vk_id,
                    message=(
                        "⚠️ **ВНИМАНИЕ! ВЫБРОС!**\n\n"
                        "Зона предупреждает: через 15 минут начнётся Выброс!\n"
                        f"Ты в укрытии ({location}) — ты в безопасности.\n\n"
                        "🛡️ Укрытия: Город, Больница, Убежище\n\n"
                        "Если ты в Зоне — срочно возвращайся в укрытие!"
                    ),
                    random_id=0,
                )
            except Exception as e:
                logger.error("Выброс #%d: не удалось отправить warning (safe) игроку %s: %s", emission_id, vk_id, e)
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

            try:
                vk.messages.send(
                    user_id=vk_id,
                    message=emission_event["text"],
                    keyboard=create_emission_warning_keyboard().get_keyboard(),
                    random_id=0,
                )
            except Exception as e:
                logger.error("Выброс #%d: не удалось отправить warning игроку %s: %s", emission_id, vk_id, e)

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

    # Handle both warning and impact phases
    phase = event.get("phase")
    if phase == "warning":
        return _handle_warning_choice(player, vk, user_id, event, text)
    elif phase == "impact":
        return _handle_impact_choice(player, vk, user_id, event, text)

    return False


def _handle_warning_choice(player, vk, user_id: int, event: dict, text: str) -> bool:
    """Обработать выбор на фазе предупреждения"""
    text_lower = text.strip().lower()

    # Пропуск
    if text_lower in ("пропустить", "skip"):
        clear_emission_pending(user_id)
        vk.messages.send(
            user_id=user_id,
            message="Зона запомнит твою смелость... или глупость.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
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
        return False

    choice = event["choices"][choice_idx]
    clear_emission_pending(user_id)

    if choice["effect"].get("flee_to_safe"):
        return _flee_to_safe_location(player, vk, user_id)

    elif choice["effect"].get("stay_and_risk"):
        vk.messages.send(
            user_id=user_id,
            message=(
                "😰 Ты решил остаться в Зоне...\n\n"
                "Выброс не будет щадить. Готовься к последствиям.\n"
                "🩺 Попробуй восстановить HP перед ударом!"
            ),
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )

    return True


def _handle_impact_choice(player, vk, user_id: int, event: dict, text: str) -> bool:
    """Обработать выбор на фазе удара (impact)"""
    text_lower = text.strip().lower()

    if text_lower in ("пропустить", "skip"):
        clear_emission_pending(user_id)
        vk.messages.send(
            user_id=user_id,
            message="Выброс бушует. Надеюсь, ты найдёшь укрытие...",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return True

    # "Бежать в укрытие" during impact
    if "бежать" in text_lower or "укрытие" in text_lower:
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

    return False


def _flee_to_safe_location(player, vk, user_id: int) -> bool:
    """Переместить игрока в случайное безопасное место"""
    import random
    safe_location = random.choice(SAFE_LOCATIONS)

    player.current_location_id = safe_location
    player.energy = max(0, player.energy - 10)  # Затраты энергии на бегство

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

    for player_data in players:
        vk_id = player_data["vk_id"]
        location = player_data.get("location", "город")
        current_health = player_data.get("health", 100)

        if location in SAFE_LOCATIONS:
            safe += 1
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
            radiation=min(100, player_data.get("radiation", 0) + radiation),
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
        try:
            vk.messages.send(
                user_id=vk_id,
                message=impact_event["text"],
                keyboard=create_emission_impact_keyboard(location).get_keyboard(),
                random_id=0,
            )
        except Exception as e:
            logger.error("Выброс #%d: не удалось отправить impact игроку %s: %s", emission_id, vk_id, e)

    logger.info(
        "Выброс #%d: удар применён. Повреждено: %d, погибло: %d, в безопасности: %d",
        emission_id, damaged, died, safe,
    )


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

        try:
            vk.messages.send(
                user_id=vk_id,
                message=random.choice(cancel_messages),
                random_id=0,
            )
        except Exception:
            pass

    logger.info("Выброс #%d: отменён, сообщения отправлены", emission_id)


def _announce_aftermath(vk, emission_id: int):
    """Объявить о фазе последствий — бонусы для всех"""
    players = database.get_all_active_players()

    for player_data in players:
        vk_id = player_data["vk_id"]
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
            pass

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
    player.radiation = min(100, player.radiation + config.EMISSION_RADIATION)

    database.update_user_stats(
        user_id,
        health=player.health,
        radiation=player.radiation,
    )

    try:
        vk.messages.send(
            user_id=user_id,
            message=(
                f"☢️ **ВЫБРОС БУШУЕТ!**\n\n"
                f"Ты в Зоне ({location}) и получаешь урон!\n"
                f"💔 Урон: -{damage} HP\n"
                f"❤️ HP: {player.health}\n"
                f"☢️ Радиация: +{config.EMISSION_RADIATION}\n\n"
                "Беги в укрытие!"
            ),
            random_id=0,
        )
    except Exception:
        pass

    return True
