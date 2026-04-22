"""
Обработчики локаций и навигации
"""
from __future__ import annotations

import logging
from pathlib import Path
import random
import time
from typing import Optional
from infra import database
from game.constants import RESEARCH_LOCATIONS, NPC_LOCATIONS, SAFE_LOCATIONS

logger = logging.getLogger(__name__)

# Кулдаун рандомных событий
EVENT_COOLDOWN_SECONDS = 30 * 60        # 30 минут — базовый кулдаун
EVENT_CHANCE_RAMP_UP = 10 * 60          # каждые 10 минут после кулдауна
EVENT_CHANCE_INCREMENT = 1.5            # +1.5% шанс за каждый интервал
EVENT_MAX_CHANCE = 100                  # макс шанс

# Коридор перемещения
TRAVEL_DEFAULT_SECONDS = 45
TRAVEL_MIN_SECONDS = 15
TRAVEL_ACCELERATION_SECONDS = 15
TRAVEL_ACCELERATION_ENERGY = 8
TRAVEL_SCOUT_COOLDOWN = 15
TRAVEL_MAX_COMBAT_ENCOUNTERS = 1
TRAVEL_EVENT_CHANCE = 18
TRAVEL_EVENT_CHANCE_FORCED = 28
TRAVEL_ENEMY_CHANCE = 30
TRAVEL_ENEMY_CHANCE_FORCED = 42
TRAVEL_POST_EMISSION_ELITE_CHANCE = 0.12
SHELTER_REGEN_TS_FLAG = "shelter_energy_regen_ts"
SHELTER_REGEN_ACTIVE_FLAG = "shelter_energy_regen_active"
HEAL_QUOTE_RUNTIME_KEY = "pending_hospital_heal_quote"
HEAL_QUOTE_TTL_SEC = 120
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_LOCATION_IMAGE_ATTACHMENT_CACHE: dict[str, str] = {}


def _get_location_image_path(image_name: str) -> Path:
    for directory in ("img", "Img"):
        image_path = PROJECT_ROOT / directory / image_name
        if image_path.exists():
            return image_path
    return PROJECT_ROOT / "img" / image_name


def _upload_location_image(vk, user_id: int, location_id: str) -> str | None:
    """Загрузить картинку локации в VK и вернуть attachment."""
    if location_id in _LOCATION_IMAGE_ATTACHMENT_CACHE:
        return _LOCATION_IMAGE_ATTACHMENT_CACHE[location_id]

    from models.locations import get_location

    loc = get_location(location_id)
    image_name = loc.image if loc else None
    if not image_name:
        return None

    image_path = _get_location_image_path(image_name)
    if not image_path.exists():
        logger.warning("Картинка локации не найдена: location=%s path=%s", location_id, image_path)
        return None

    try:
        import requests

        upload_server = vk.photos.getMessagesUploadServer(peer_id=user_id)
        with image_path.open("rb") as image_file:
            upload_response = requests.post(
                upload_server["upload_url"],
                files={"photo": image_file},
                timeout=20,
            )
        upload_response.raise_for_status()
        uploaded = upload_response.json()
        saved = vk.photos.saveMessagesPhoto(
            photo=uploaded["photo"],
            server=uploaded["server"],
            hash=uploaded["hash"],
        )
        if not saved:
            return None

        photo = saved[0]
        attachment = f"photo{photo['owner_id']}_{photo['id']}"
        access_key = photo.get("access_key")
        if access_key:
            attachment = f"{attachment}_{access_key}"

        _LOCATION_IMAGE_ATTACHMENT_CACHE[location_id] = attachment
        return attachment
    except Exception:
        logger.exception("Не удалось загрузить картинку локации: user_id=%s location=%s", user_id, location_id)
        return None


def _send_location_message(vk, user_id: int, location_id: str, message: str, keyboard):
    """Отправить описание локации с картинкой, если она есть."""
    send_kwargs = {
        "user_id": user_id,
        "message": message,
        "keyboard": keyboard,
        "random_id": 0,
    }

    attachment = _upload_location_image(vk, user_id, location_id)
    if attachment:
        send_kwargs["attachment"] = attachment

    try:
        vk.messages.send(**send_kwargs)
    except Exception:
        if "attachment" not in send_kwargs:
            raise
        logger.exception("Не удалось отправить локацию с картинкой, повторяю без attachment")
        send_kwargs.pop("attachment", None)
        vk.messages.send(**send_kwargs)


def _should_use_travel_corridor(from_location: str, to_location: str) -> bool:
    """Коридор нужен только для переходов, связанных с лут-локациями Зоны."""
    return from_location in RESEARCH_LOCATIONS or to_location in RESEARCH_LOCATIONS


def _normalize_last_event_time(raw_value, now: int) -> int:
    """Нормализовать last_random_event_time к unix timestamp в секундах."""
    try:
        ts = int(raw_value or 0)
    except (TypeError, ValueError):
        return 0

    if ts <= 0:
        return 0

    # Иногда значение может быть в миллисекундах.
    if ts > 10_000_000_000:
        ts = ts // 1000

    # Защита от "времени из будущего" (сдвиг часов/битые данные).
    if ts > now:
        return 0

    return ts


def get_event_spawn_state(last_event_time_raw, now: Optional[int] = None) -> dict:
    """
    Рассчитать текущее состояние выдачи рандом-события.

    Возвращает словарь:
    {
        "last_event_time": int,
        "elapsed": int,
        "cooldown_remaining": int,
        "chance": float,
        "ready": bool,
    }
    """
    if now is None:
        now = int(time.time())

    last_event_time = _normalize_last_event_time(last_event_time_raw, now)

    if last_event_time == 0:
        return {
            "last_event_time": 0,
            "elapsed": 0,
            "cooldown_remaining": 0,
            "chance": 100.0,
            "ready": True,
        }

    elapsed = max(0, now - last_event_time)
    if elapsed < EVENT_COOLDOWN_SECONDS:
        return {
            "last_event_time": last_event_time,
            "elapsed": elapsed,
            "cooldown_remaining": EVENT_COOLDOWN_SECONDS - elapsed,
            "chance": 0.0,
            "ready": False,
        }

    time_after_cooldown = elapsed - EVENT_COOLDOWN_SECONDS
    intervals_passed = int(time_after_cooldown / EVENT_CHANCE_RAMP_UP)
    chance = min(EVENT_MAX_CHANCE, intervals_passed * EVENT_CHANCE_INCREMENT)

    return {
        "last_event_time": last_event_time,
        "elapsed": elapsed,
        "cooldown_remaining": 0,
        "chance": float(chance),
        "ready": True,
    }


def _check_event_cooldown(user_id: int) -> bool:
    """
    Проверить кулдаун рандомных событий.
    Возвращает True если можно выдавать событие, False если на кулдауне.

    Механика:
    - После получения события — кулдаун 30 минут
    - После кулдауна — шанс растёт на 1.5% каждые 10 минут
    - Максимум 100%
    """
    state = get_event_spawn_state(database.get_user_flag(user_id, "last_random_event_time", 0))
    if not state["ready"]:
        logger.debug(
            "random_event cooldown: user=%s elapsed=%ss remaining=%ss",
            user_id, state["elapsed"], state["cooldown_remaining"],
        )
        return False

    import random
    roll = random.random() * 100
    hit = roll <= state["chance"]
    logger.debug(
        "random_event chance: user=%s elapsed=%ss chance=%.2f roll=%.2f hit=%s",
        user_id, state["elapsed"], state["chance"], roll, hit,
    )
    return hit


def _get_travel_duration_seconds(from_location: str, to_location: str) -> int:
    """Базовая длительность перехода между локациями."""
    direct = {
        ("город", "кпп"): 25,
        ("кпп", "город"): 25,
        ("город", "больница"): 20,
        ("больница", "город"): 20,
        ("город", "убежище"): 45,
        ("убежище", "город"): 45,
    }
    if (from_location, to_location) in direct:
        base = direct[(from_location, to_location)]
    elif (from_location == "кпп" and to_location in RESEARCH_LOCATIONS) or (
        to_location == "кпп" and from_location in RESEARCH_LOCATIONS
    ):
        base = 60
    elif from_location in RESEARCH_LOCATIONS and to_location in RESEARCH_LOCATIONS:
        base = 75
    else:
        base = TRAVEL_DEFAULT_SECONDS

    jitter = random.randint(-5, 7)
    return max(TRAVEL_MIN_SECONDS, base + jitter)


def _is_location_locked(user_id: int, location_id: str) -> bool:
    """Проверка ограничений входа в локацию."""
    if location_id != "убежище":
        return False

    try:
        with database.db_cursor() as (cursor, _):
            cursor.execute("SELECT newbie_kit_received FROM users WHERE vk_id = %s", (user_id,))
            row = cursor.fetchone()
            return bool(row and row["newbie_kit_received"] == 1)
    except Exception:
        logger.exception("Ошибка проверки блокировки локации: user_id=%s location=%s", user_id, location_id)
        # Fail-open: лучше не блокировать игрока из-за временной ошибки БД.
        return False


def _validate_travel_state(travel: dict | None) -> tuple[bool, str]:
    """Быстрая валидация структуры travel-state перед тиками/командами."""
    if not isinstance(travel, dict):
        return False, "state_not_dict"
    for key in ("from_location", "to_location", "start_time", "duration"):
        if key not in travel:
            return False, f"missing_{key}"

    from_location = str(travel.get("from_location") or "")
    to_location = str(travel.get("to_location") or "")
    if not from_location or not to_location:
        return False, "empty_route"

    try:
        duration = int(travel.get("duration", 0) or 0)
    except (TypeError, ValueError):
        return False, "bad_duration"
    if duration <= 0:
        return False, "non_positive_duration"

    try:
        float(travel.get("start_time", 0) or 0)
    except (TypeError, ValueError):
        return False, "bad_start_time"

    return True, "ok"


def _send_location_overview(player, vk, user_id: int, location_id: str):
    """Показать описание локации без мгновенных случайных событий при входе."""
    from main import create_location_keyboard
    loc = player.location
    player_level = player.level if hasattr(player, "level") else None

    npc_message = ""
    npcs = NPC_LOCATIONS.get(location_id, [])
    if npcs:
        npc_list = ", ".join([f"{npc}" for npc in npcs])
        npc_message = f"\n\nNPC: {npc_list}"

    location_info = ""
    from game.location_mechanics import get_location_modifier, get_zone_mutation_state
    from game.limited_events import get_active_limited_event, get_limited_event_modifiers
    mod = get_location_modifier(location_id)
    if mod:
        parts = []
        if mod.get("danger_mult", 1.0) > 1.0:
            parts.append(f"⚠️ Опасность +{int((mod['danger_mult'] - 1.0) * 100)}%")
        if mod.get("find_chance_mult", 1.0) > 1.0:
            parts.append(f"🔍 Находки +{int((mod['find_chance_mult'] - 1.0) * 100)}%")
        if mod.get("radiation_mult", 1.0) > 1.0:
            parts.append(f"☢️ Радиация +{int((mod['radiation_mult'] - 1.0) * 100)}%")
        if mod.get("energy_cost_mult", 1.0) > 1.0:
            parts.append(f"⚡ Энергия +{int((mod['energy_cost_mult'] - 1.0) * 100)}%")

        mutation_state = get_zone_mutation_state(location_id)
        if mutation_state.get("active"):
            parts.append(f"🌀 **МУТАЦИЯ ЗОНЫ!** Находки +{int(mutation_state['bonus_find'] * 100)}%")

        limited = get_active_limited_event()
        if limited:
            mods = get_limited_event_modifiers()
            find_bonus = int(round((float(mods.get("research_find_mult", 1.0) or 1.0) - 1.0) * 100))
            danger_bonus = int(round((float(mods.get("research_danger_mult", 1.0) or 1.0) - 1.0) * 100))
            art_bonus = int(round((float(mods.get("artifact_event_mult", 1.0) or 1.0) - 1.0) * 100))
            enemy_bonus = int(round((float(mods.get("enemy_event_mult", 1.0) or 1.0) - 1.0) * 100))
            mins_left = max(0, int(limited.get("seconds_left", 0) or 0) // 60)
            parts.append(f"🌐 Ивент: {limited.get('name', 'Событие Зоны')} (ещё ~{mins_left} мин)")
            parts.append(
                f"🔍 Ивент {find_bonus:+d}% | ⚠️ Ивент {danger_bonus:+d}% | "
                f"💎 Ивент {art_bonus:+d}% | 👾 Ивент {enemy_bonus:+d}%"
            )

        if parts:
            location_info = f"\n\n📊 **Активные модификаторы:**\n" + "\n".join(f"• {p}" for p in parts)

    _send_location_message(
        vk,
        user_id,
        location_id,
        f"{loc.name}\n\n{loc.description}{npc_message}{location_info}",
        create_location_keyboard(location_id, player_level).get_keyboard(),
    )


def _arrive_to_location(player, vk, user_id: int, location_id: str, from_location: str):
    """Финализировать переход и показать локацию."""
    from handlers.quests import track_quest_explore, track_quest_visit
    from infra.state_manager import clear_travel_state, set_ui_screen

    clear_travel_state(user_id)

    if from_location not in ["инвентарь"]:
        player.previous_location = from_location
        database.update_user_stats(user_id, previous_location=from_location)

    player.current_location_id = location_id
    database.update_user_location(user_id, location_id)
    # Фиксируем якорь пассивного регена энергии по факту прибытия в локацию.
    now_ts = int(time.time())
    database.set_user_flag(user_id, SHELTER_REGEN_TS_FLAG, now_ts)
    database.set_user_flag(user_id, SHELTER_REGEN_ACTIVE_FLAG, 1 if location_id == "убежище" else 0)
    set_ui_screen(user_id, {"name": "location"}, clear_stack=True)

    track_quest_visit(user_id, location_id, vk=vk)
    if location_id in RESEARCH_LOCATIONS:
        track_quest_explore(user_id, location_id, vk=vk)

    _send_location_overview(player, vk, user_id, location_id)


def _maybe_trigger_travel_event(player, vk, user_id: int, travel: dict, forced: bool = False) -> bool:
    """
    Сгенерировать событие в коридоре перехода.
    Возвращает True если сгенерирован интерактивный контент (бой/ивент).
    """
    from infra.state_manager import set_pending_event, update_travel_data
    from game.random_events import get_random_event, format_event_message
    from handlers.keyboards import create_random_event_keyboard
    from handlers.combat import _spawn_enemy
    from game.emission import is_emission_rare_enemy_bonus

    roll = random.randint(1, 100)
    event_threshold = TRAVEL_EVENT_CHANCE_FORCED if forced else TRAVEL_EVENT_CHANCE
    enemy_threshold = TRAVEL_ENEMY_CHANCE_FORCED if forced else TRAVEL_ENEMY_CHANCE
    combat_encounters = int(travel.get("combat_encounters", 0) or 0)
    max_combat_encounters = int(travel.get("max_combat_encounters", TRAVEL_MAX_COMBAT_ENCOUNTERS) or TRAVEL_MAX_COMBAT_ENCOUNTERS)

    # 1) Ивент
    if roll <= event_threshold and _check_event_cooldown(user_id):
        event = get_random_event(user_id=user_id)
        if event:
            set_pending_event(user_id, event)
            database.set_user_flag(user_id, "last_random_event_time", int(time.time()))
            vk.messages.send(
                user_id=user_id,
                message=(
                    "🧭 В пути происходит событие...\n\n"
                    f"{format_event_message(event)}"
                ),
                keyboard=create_random_event_keyboard(event).get_keyboard(),
                random_id=0,
            )
            return True

    # 2) Бой в пути
    if combat_encounters < max_combat_encounters and roll <= enemy_threshold:
        encounter_loc = travel.get("to_location")
        if encounter_loc not in RESEARCH_LOCATIONS:
            encounter_loc = travel.get("from_location")
        if encounter_loc in RESEARCH_LOCATIONS:
            allow_elite = False
            if is_emission_rare_enemy_bonus() and random.random() < TRAVEL_POST_EMISSION_ELITE_CHANCE:
                allow_elite = True
            original_loc = player.current_location_id
            try:
                player.current_location_id = encounter_loc
                vk.messages.send(
                    user_id=user_id,
                    message="🚨 Засада в коридоре перехода! Будь готов к бою.",
                    random_id=0,
                )
                _spawn_enemy(player, vk, user_id, allow_elite=allow_elite)
                update_travel_data(user_id, {"combat_encounters": combat_encounters + 1})
                return True
            finally:
                player.current_location_id = original_loc

    return False


def _travel_progress(travel: dict, now_ts: float) -> tuple[float, int]:
    duration = max(1, int(travel.get("duration", TRAVEL_DEFAULT_SECONDS)))
    start_time = float(travel.get("start_time", now_ts))
    paused_total = float(travel.get("paused_total", 0.0))
    pause_started_at = travel.get("pause_started_at")
    paused_now = 0.0
    if pause_started_at:
        paused_now = max(0.0, now_ts - float(pause_started_at))
    elapsed = max(0.0, now_ts - start_time - paused_total - paused_now)
    progress = min(1.0, elapsed / duration)
    remaining = max(0, int(duration - elapsed))
    return progress, remaining


def travel_tick(player, vk, user_id: int, silent: bool = True) -> bool:
    """Тик коридора перехода. Возвращает True если переход ещё активен."""
    from infra.state_manager import (
        get_travel_data, update_travel_data, clear_travel_state,
        has_pending_event, has_emission_pending,
        is_in_combat, is_in_anomaly, is_in_dialog,
    )
    from handlers.keyboards import create_travel_keyboard

    travel = get_travel_data(user_id)
    if not travel:
        return False
    valid, reason = _validate_travel_state(travel)
    if not valid:
        logger.warning("Сброс повреждённого travel_state user_id=%s reason=%s data=%r", user_id, reason, travel)
        clear_travel_state(user_id)
        if not silent:
            vk.messages.send(
                user_id=user_id,
                message="⚠️ Переход сброшен из-за некорректного состояния. Запусти путь заново.",
                random_id=0,
            )
        return False

    now_ts = time.time()

    # Блокирующие состояния: пауза коридора
    if is_in_combat(user_id) or is_in_anomaly(user_id) or has_pending_event(user_id) or has_emission_pending(user_id) or is_in_dialog(user_id):
        if not travel.get("pause_started_at"):
            update_travel_data(user_id, {"pause_started_at": now_ts})
            travel = get_travel_data(user_id) or travel
        progress, _ = _travel_progress(travel, now_ts)
        if not silent:
            vk.messages.send(
                user_id=user_id,
                message=(
                    f"🧭 Переход приостановлен ({int(progress * 100)}%).\n"
                    "Заверши текущее событие, и путь продолжится."
                ),
                keyboard=create_travel_keyboard().get_keyboard(),
                random_id=0,
            )
        return True

    # Выходим из паузы и фиксируем накопленное время простоя.
    pause_started_at = travel.get("pause_started_at")
    if pause_started_at:
        paused_delta = max(0.0, now_ts - float(pause_started_at))
        update_travel_data(
            user_id,
            {
                "paused_total": float(travel.get("paused_total", 0.0)) + paused_delta,
                "pause_started_at": None,
            },
        )
        travel = get_travel_data(user_id) or travel

    progress, remaining = _travel_progress(travel, now_ts)

    # Авто-чекпоинты по прогрессу
    checkpoints = travel.get("checkpoints", [0.35, 0.75])
    passed = travel.get("passed_checkpoints", 0)
    while passed < len(checkpoints) and progress >= checkpoints[passed]:
        triggered = _maybe_trigger_travel_event(player, vk, user_id, travel, forced=False)
        passed += 1
        update_travel_data(user_id, {"passed_checkpoints": passed})
        if triggered:
            return True

    # Завершение маршрута
    if remaining <= 0:
        _arrive_to_location(player, vk, user_id, travel["to_location"], travel["from_location"])
        return False

    if not silent:
        vk.messages.send(
            user_id=user_id,
            message=(
                f"🧭 Ты в пути: {travel['from_location']} → {travel['to_location']}\n"
                f"Прогресс: {int(progress * 100)}%\n"
                f"Осталось: ~{remaining} сек"
            ),
            keyboard=create_travel_keyboard().get_keyboard(),
            random_id=0,
        )

    return True


def handle_travel_commands(player, vk, user_id: int, text: str) -> bool:
    """Команды внутри коридора перехода."""
    from infra.state_manager import has_travel_state, get_travel_data, update_travel_data, clear_travel_state, set_ui_screen
    from handlers.keyboards import create_travel_keyboard
    from main import create_location_keyboard

    if not has_travel_state(user_id):
        return False

    travel = get_travel_data(user_id)
    if not travel:
        return False
    valid, reason = _validate_travel_state(travel)
    if not valid:
        logger.warning("Команда в повреждённом travel_state user_id=%s reason=%s data=%r", user_id, reason, travel)
        clear_travel_state(user_id)
        vk.messages.send(
            user_id=user_id,
            message="⚠️ Переход сброшен из-за некорректного состояния. Запусти путь заново.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return True

    text_lower = (text or "").strip().lower()

    if text_lower in ("отмена пути", "прервать путь", "отмена", "вернуться"):
        from_location = str(travel.get("from_location") or player.current_location_id)
        clear_travel_state(user_id)
        set_ui_screen(user_id, {"name": "location"}, clear_stack=True)
        if player.current_location_id != from_location:
            player.current_location_id = from_location
            database.update_user_location(user_id, from_location)
        vk.messages.send(
            user_id=user_id,
            message="↩️ Ты отменил переход и вернулся на исходную позицию.",
            keyboard=create_location_keyboard(from_location, player.level).get_keyboard(),
            random_id=0,
        )
        return True

    if "ускор" in text_lower:
        now_ts = time.time()
        progress, remaining = _travel_progress(travel, now_ts)
        if remaining <= 6:
            vk.messages.send(
                user_id=user_id,
                message="⚡ Ты уже почти на месте, ускорение не требуется.",
                keyboard=create_travel_keyboard().get_keyboard(),
                random_id=0,
            )
            return True
        passive = player._get_passive_bonuses() if hasattr(player, "_get_passive_bonuses") else {}
        accel_discount = max(0, int(passive.get("travel_acceleration_energy_reduction", 0) or 0))
        acceleration_energy = max(1, TRAVEL_ACCELERATION_ENERGY - accel_discount)
        if player.energy < acceleration_energy:
            vk.messages.send(
                user_id=user_id,
                message=f"⚡ Не хватает энергии. Нужно {acceleration_energy}, у тебя {player.energy}.",
                keyboard=create_travel_keyboard().get_keyboard(),
                random_id=0,
            )
            return True
        cut = min(TRAVEL_ACCELERATION_SECONDS, max(0, remaining - 5))
        if cut <= 0:
            return travel_tick(player, vk, user_id, silent=False)
        player.energy -= acceleration_energy
        database.update_user_stats(user_id, energy=player.energy)
        new_duration = max(TRAVEL_MIN_SECONDS, int(travel.get("duration", TRAVEL_DEFAULT_SECONDS)) - cut)
        update_travel_data(user_id, {"duration": new_duration})
        vk.messages.send(
            user_id=user_id,
            message=(
                f"🏃 Ты ускорился! -{acceleration_energy}⚡\n"
                f"Время в пути сокращено на {cut} сек."
            ),
            keyboard=create_travel_keyboard().get_keyboard(),
            random_id=0,
        )
        return travel_tick(player, vk, user_id, silent=False)

    if "осмотр" in text_lower:
        now_ts = time.time()
        last_scout = int(travel.get("last_scout_time", 0))
        passive = player._get_passive_bonuses() if hasattr(player, "_get_passive_bonuses") else {}
        scout_cd_reduction = max(0, int(passive.get("travel_scout_cooldown_reduction", 0) or 0))
        scout_cooldown = max(10, TRAVEL_SCOUT_COOLDOWN - scout_cd_reduction)
        if last_scout and now_ts - last_scout < scout_cooldown:
            wait_left = int(scout_cooldown - (now_ts - last_scout))
            vk.messages.send(
                user_id=user_id,
                message=f"👀 Осмотреться можно чуть позже. Подожди {wait_left} сек.",
                keyboard=create_travel_keyboard().get_keyboard(),
                random_id=0,
            )
            return True
        update_travel_data(user_id, {"last_scout_time": now_ts})
        triggered = _maybe_trigger_travel_event(player, vk, user_id, travel, forced=True)
        if not triggered:
            vk.messages.send(
                user_id=user_id,
                message="🌫️ Ты осмотрелся, но коридор пока тихий.",
                keyboard=create_travel_keyboard().get_keyboard(),
                random_id=0,
            )
        return True

    # Любой ввод в пути — это запрос статуса/продолжения.
    return travel_tick(player, vk, user_id, silent=False)


def go_to_location(player, location_id: str, vk, user_id: int, bypass_risk_confirm: bool = False):
    """Запустить переход в локацию через коридор перемещения."""
    from handlers.keyboards import create_travel_keyboard
    from infra.state_manager import has_travel_state, set_travel_state, set_ui_screen
    from main import create_location_keyboard

    if has_travel_state(user_id):
        vk.messages.send(
            user_id=user_id,
            message="🧭 Ты уже в пути. Используй команды коридора перехода.",
            keyboard=create_travel_keyboard().get_keyboard(),
            random_id=0,
        )
        return

    from_location = player.current_location_id
    if from_location == "инвентарь" and player.previous_location:
        from_location = player.previous_location

    if not bypass_risk_confirm:
        try:
            from game.emission import prompt_emission_risk_exit_confirmation
            if prompt_emission_risk_exit_confirmation(player, vk, user_id, from_location, location_id):
                return
        except Exception:
            logger.exception("Не удалось запросить подтверждение риска выхода из safe: user_id=%s", user_id)

    # Если игрок вышел из укрытия во время impact — возврат в safe закрыт до конца impact.
    try:
        from game.emission import mark_emission_safe_exit_during_impact
        mark_emission_safe_exit_during_impact(user_id, from_location, location_id)
    except Exception:
        logger.exception("Не удалось отметить выход из safe в impact: user_id=%s", user_id)

    if location_id == from_location:
        set_ui_screen(user_id, {"name": "location"}, clear_stack=True)
        vk.messages.send(
            user_id=user_id,
            message="Ты уже находишься в этой локации.",
            keyboard=create_location_keyboard(from_location, player.level).get_keyboard(),
            random_id=0,
        )
        return

    if location_id in SAFE_LOCATIONS:
        from game.emission import is_emission_safe_entry_blocked_for_user
        blocked, seconds_to_impact = is_emission_safe_entry_blocked_for_user(user_id)
        # Во время impact разрешаем перемещение ВНУТРИ safe-зон (город/больница/убежище).
        # Блокируем только вход в safe из опасных локаций.
        if blocked and from_location not in SAFE_LOCATIONS:
            mins = max(0, seconds_to_impact // 60)
            vk.messages.send(
                user_id=user_id,
                message=(
                    "☢️ Вход в безопасные зоны закрыт.\n\n"
                    "Ты выбрал остаться в Зоне во время предупреждения о выбросе.\n"
                    "Теперь до конца выброса отступление невозможно.\n"
                    f"До удара: ~{mins} мин."
                ),
                keyboard=create_location_keyboard(from_location, player.level).get_keyboard(),
                random_id=0,
            )
            return

    if _is_location_locked(user_id, location_id):
        set_ui_screen(user_id, {"name": "location"}, clear_stack=True)
        vk.messages.send(
            user_id=user_id,
            message=(
                "УБЕЖИЩЕ ЗАКРЫТО\n\n"
                "Вход закрыт. Местный житель предупреждал — после получения набора "
                "ты должен выживать в Зоне сам.\n\n"
                "Иди на КПП -> в Зону."
            ),
            keyboard=create_location_keyboard("город").get_keyboard(),
            random_id=0,
        )
        return

    # Безопасные переходы (внутри города/хабов) оставляем мгновенными.
    if not _should_use_travel_corridor(from_location, location_id):
        _arrive_to_location(player, vk, user_id, location_id, from_location)
        return

    base_duration = _get_travel_duration_seconds(from_location, location_id)
    passive = player._get_passive_bonuses() if hasattr(player, "_get_passive_bonuses") else {}
    travel_reduction_pct = max(0, min(60, int(passive.get("travel_time_reduction_pct", 0) or 0)))
    duration = base_duration
    if travel_reduction_pct > 0:
        duration = max(TRAVEL_MIN_SECONDS, int(base_duration * (100 - travel_reduction_pct) / 100))
    now_ts = time.time()
    eta = now_ts + duration
    checkpoints = [0.35, 0.75] if duration >= 35 else [0.6]

    set_travel_state(user_id, {
        "from_location": from_location,
        "to_location": location_id,
        "start_time": now_ts,
        "duration": duration,
        "eta": eta,
        "checkpoints": checkpoints,
        "passed_checkpoints": 0,
        "last_scout_time": 0,
        "paused_total": 0.0,
        "pause_started_at": None,
        "seed": random.randint(1, 10_000_000),
        "resolved_checkpoints": [],
        "combat_encounters": 0,
        "max_combat_encounters": TRAVEL_MAX_COMBAT_ENCOUNTERS,
    })

    vk.messages.send(
        user_id=user_id,
        message=(
            f"🧭 Ты отправился в путь: {from_location} → {location_id}\n"
            f"⏱️ Примерное время: {duration} сек"
            + (f" (маршрут сокращён на {travel_reduction_pct}%)" if travel_reduction_pct > 0 else "")
            + "\n\n"
            "По дороге могут случиться события. "
            "Используй 'Осмотреться' для рискованной разведки."
        ),
        keyboard=create_travel_keyboard().get_keyboard(),
        random_id=0,
    )


def go_to_inventory(player, vk, user_id: int):
    """Открыть инвентарь - показать все категории"""
    from infra.state_manager import get_ui_current_screen, set_ui_screen
    from handlers.inventory import show_all

    # Сохраняем текущую локацию как предыдущую (для возврата из инвентаря)
    if player.current_location_id not in ["инвентарь"]:
        player.previous_location = player.current_location_id
        database.update_user_stats(user_id, previous_location=player.current_location_id)

    player.current_location_id = "инвентарь"
    database.update_user_location(user_id, "инвентарь")
    current_ui = get_ui_current_screen(user_id)
    push_current = current_ui.get("name") != "inventory"
    set_ui_screen(user_id, {"name": "inventory"}, push_current=push_current)
    
    # Показываем весь инвентарь по категориям
    show_all(player, vk, user_id)


def go_back(player, vk, user_id: int):
    """Вернуться к предыдущему UI-экрану."""
    from main import create_location_keyboard
    from handlers.inventory import show_all
    from handlers.keyboards import create_character_keyboard
    from infra.state_manager import pop_ui_screen, set_ui_screen

    prev_screen = pop_ui_screen(user_id)
    if prev_screen:
        name = prev_screen.get("name")
        if name == "character":
            vk.messages.send(
                user_id=user_id,
                message="👤 ПЕРСОНАЖ\nВыбери раздел:",
                keyboard=create_character_keyboard().get_keyboard(),
                random_id=0
            )
            return
        if name == "inventory":
            if player.current_location_id != "инвентарь":
                player.previous_location = player.current_location_id
                database.update_user_stats(user_id, previous_location=player.current_location_id)
            player.current_location_id = "инвентарь"
            database.update_user_location(user_id, "инвентарь")
            show_all(player, vk, user_id)
            return
        # location/fallback
        if player.current_location_id == "инвентарь":
            target_location = player.previous_location or "кпп"
            player.current_location_id = target_location
            database.update_user_location(user_id, target_location)
        _send_location_message(
            vk,
            user_id,
            player.current_location_id,
            f"📍 {player.location.name}\n\n{player.location.description}",
            create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
        )
        return

    # Если стек пуст — безопасный fallback в локационный экран
    set_ui_screen(user_id, {"name": "location"}, clear_stack=True)
    if player.current_location_id == "инвентарь":
        target_location = player.previous_location or "кпп"
        player.current_location_id = target_location
        database.update_user_location(user_id, target_location)
    elif player.previous_location and player.previous_location != player.current_location_id:
        player.current_location_id = player.previous_location
        database.update_user_location(user_id, player.previous_location)
    _send_location_message(
        vk,
        user_id,
        player.current_location_id,
        f"📍 {player.location.name}\n\n{player.location.description}",
        create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
    )


def handle_sleep(player, vk, user_id: int):
    """Спать в убежище"""
    from main import create_location_keyboard
    from models.player import format_radiation_rate, get_radiation_stage
    from infra import config
    
    if player.current_location_id == "убежище":
        now = int(time.time())
        cooldown = int(getattr(config, "SHELTER_SLEEP_COOLDOWN_SEC", 3 * 60 * 60) or (3 * 60 * 60))
        last_sleep = int(database.get_user_flag(user_id, "shelter_sleep_last", 0) or 0)

        if last_sleep and now - last_sleep < cooldown:
            left = cooldown - (now - last_sleep)
            hours = left // 3600
            minutes = (left % 3600) // 60
            wait_text = f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"
            vk.messages.send(
                user_id=user_id,
                message=(
                    "🛏️ Ты уже отдыхал недавно.\n\n"
                    f"Следующий полноценный сон будет доступен через {wait_text}."
                ),
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
            return

        old_hp = int(player.health)
        old_energy = int(player.energy)
        old_rad = int(player.radiation)

        hp_heal = max(12, int(player.max_health * 0.18))
        energy_heal = 35
        rad_reduce = 10

        new_hp = min(player.max_health, old_hp + hp_heal)
        new_energy = min(100, old_energy + energy_heal)
        new_rad = max(0, old_rad - rad_reduce)

        # Если и так всё в порядке — даём только лёгкий восстановительный тик.
        if new_hp == old_hp and new_energy == old_energy and new_rad == old_rad:
            new_energy = min(100, old_energy + 8)

        player.health = new_hp
        player.energy = new_energy
        player.radiation = new_rad

        database.update_user_stats(
            user_id,
            health=new_hp,
            energy=new_energy,
            radiation=new_rad,
        )
        database.set_user_flag(user_id, "shelter_sleep_last", now)

        message = (
            "🛏️ Ты устроился в убежище и немного выспался.\n\n"
            f"❤️ HP: {old_hp} → {new_hp}/{player.max_health}\n"
            f"⚡ Энергия: {old_energy} → {new_energy}/100\n"
            f"☢️ Радиация: {old_rad} → {new_rad} ед.\n"
            f"   ({format_radiation_rate(old_rad)} → {format_radiation_rate(new_rad)})\n"
            f"🧪 Стадия: {get_radiation_stage(new_rad)['name']}\n\n"
            "Сон в Зоне тревожный, но силы восстановлены."
        )
        vk.messages.send(
            user_id=user_id,
            message=message,
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
    elif player.current_location_id == "больница":
        vk.messages.send(user_id=user_id, message="Здесь нельзя спать. Лучше иди в Убежище.", random_id=0)
    else:
        vk.messages.send(user_id=user_id, message="Небезопасно спать здесь. Найди убежище.", random_id=0)


def _get_player_rank_info(player) -> tuple[int, str, int]:
    """Вернуть тир, название и минимальный уровень текущего ранга."""
    tier = 1
    try:
        getter = getattr(player, "_get_rank_tier", None)
        if callable(getter):
            tier = int(getter() or 1)
    except Exception:
        tier = 1

    rank_tiers = getattr(player, "RANK_TIERS", []) or []
    tier = max(1, min(len(rank_tiers) or 1, tier))
    if not rank_tiers:
        return tier, "Новичок", 1

    rank = rank_tiers[tier - 1]
    return tier, str(rank.get("name", "Новичок")), int(rank.get("min_level", 1) or 1)


def calculate_hospital_treatment_price(
    player_level: int,
    rank_tier: int,
    missing_hp: int,
    missing_energy: int,
    treatment_count: int,
    rank_min_level: int = 1,
) -> dict:
    """
    Посчитать цену лечения.

    Цена зависит от фактически восстановленных HP/энергии, но не превышает
    персональный потолок текущего ранга. Это защищает ранние уровни от
    взрослой экономики и убирает одинаковую цену за лёгкую и тяжёлую травму.
    """
    from infra import config

    level = max(1, int(player_level or 1))
    rank = max(1, int(rank_tier or 1))
    hp = max(0, int(missing_hp or 0))
    energy = max(0, int(missing_energy or 0))
    treatments = max(0, int(treatment_count or 0))
    rank_floor = max(1, int(rank_min_level or 1))

    absolute_cap = max(0, int(getattr(config, "HEAL_PRICE_CAP", 25000) or 25000))
    if treatments == 0:
        return {"price": 0, "raw_price": 0, "cap": absolute_cap, "capped": False, "free": True}

    if hp <= 0 and energy <= 0:
        return {"price": 0, "raw_price": 0, "cap": absolute_cap, "capped": False, "free": False}

    base = max(0, int(getattr(config, "HEAL_BASE_PRICE", 80) or 80))
    hp_price = max(0, int(getattr(config, "HEAL_HP_PRICE", 6) or 6))
    energy_price = max(0, int(getattr(config, "HEAL_ENERGY_PRICE", 2) or 2))
    level_fee = max(0, int(getattr(config, "HEAL_LEVEL_FEE", 8) or 8))
    rank_fee = max(0, int(getattr(config, "HEAL_RANK_FEE", 25) or 25))

    raw_price = (
        base
        + hp * hp_price
        + energy * energy_price
        + max(0, level - 1) * level_fee
        + max(0, rank - 1) * rank_fee
    )

    rank_cap_base = max(0, int(getattr(config, "HEAL_RANK_CAP_BASE", 350) or 350))
    rank_cap_step = max(0, int(getattr(config, "HEAL_RANK_CAP_STEP", 300) or 300))
    rank_cap_level_step = max(0, int(getattr(config, "HEAL_RANK_CAP_LEVEL_STEP", 40) or 40))
    rank_cap = (
        rank_cap_base
        + max(0, rank - 1) * rank_cap_step
        + max(0, level - rank_floor) * rank_cap_level_step
    )
    cap = max(0, min(absolute_cap, rank_cap))
    price = min(raw_price, cap)
    return {
        "price": int(price),
        "raw_price": int(raw_price),
        "cap": int(cap),
        "capped": raw_price > cap,
        "free": False,
    }


def _get_pending_heal_quote(user_id: int) -> dict | None:
    payload = database.get_runtime_state(user_id, HEAL_QUOTE_RUNTIME_KEY) or {}
    if not payload:
        return None
    now_ts = int(time.time())
    ts = int(payload.get("created_at", 0) or 0)
    if ts <= 0 or (now_ts - ts) > HEAL_QUOTE_TTL_SEC:
        database.clear_runtime_state(user_id, HEAL_QUOTE_RUNTIME_KEY)
        return None
    return payload


def _set_pending_heal_quote(
    user_id: int,
    price: int,
    missing_hp: int,
    missing_energy: int,
    level: int,
    rank_tier: int,
):
    database.set_runtime_state(
        user_id,
        HEAL_QUOTE_RUNTIME_KEY,
        {
            "created_at": int(time.time()),
            "price": int(price),
            "missing_hp": int(missing_hp),
            "missing_energy": int(missing_energy),
            "level": int(level),
            "rank_tier": int(rank_tier),
        },
    )


def _execute_hospital_heal(
    player,
    vk,
    user_id: int,
    *,
    price: int,
    price_info: dict,
    rank_name: str,
    hospital_discount_pct: int,
    old_hp: int,
    old_energy: int,
    missing_hp: int,
    missing_energy: int,
    treatment_count: int,
):
    from main import create_location_keyboard

    # Проверяем, хватает ли денег
    if player.money < price:
        discount_line = (
            f"\nСкидка класса: -{hospital_discount_pct}%." if hospital_discount_pct > 0 else ""
        )
        vk.messages.send(
            user_id=user_id,
            message=(
                f"💸 Лечение стоит {price:,} руб., а у тебя {player.money:,} руб.\n\n"
                f"Цена рассчитана по травмам: +{missing_hp} HP, +{missing_energy} энергии.\n"
                f"Потолок твоего ранга ({rank_name}): {price_info['cap']:,} руб."
                f"{discount_line}"
            ),
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    # Лечим полностью здоровье и восстанавливаем энергию
    player.health = player.max_health
    player.energy = 100
    database.update_user_stats(user_id, health=player.health, energy=player.energy)

    # Списываем деньги и увеличиваем счетчик лечений
    new_money = player.money - price
    new_treatment_count = treatment_count + 1
    database.update_user_stats(user_id, money=new_money, hospital_treatments=new_treatment_count)

    # Формируем сообщение
    if bool(price_info.get("free")):
        price_text = "бесплатно (первое лечение)"
    elif price_info.get("capped"):
        price_text = (
            f"{price:,} руб. (по потолку ранга {rank_name}; "
            f"без потолка было бы {price_info['raw_price']:,} руб.)"
        )
    else:
        price_text = f"{price:,} руб. (ранг {rank_name}, уровень {player.level})"
    if hospital_discount_pct > 0 and not bool(price_info.get("free")):
        price_text += f", скидка класса -{hospital_discount_pct}%"

    message = (
        f"🏥ЛЕЧЕНИЕ В БОЛЬНИЦЕ\n\n"
        f"Врач осмотрел тебя, перевязал раны, сделал уколы.\n\n"
        f"✅ЗДОРОВЬЕ ПОЛНОСТЬЮ ВОССТАНОВЛЕНО!\n"
        f"   HP: {old_hp} → {player.health}/{player.max_health}\n\n"
        f"⚡ЭНЕРГИЯ ВОССТАНОВЛЕНА!\n"
        f"   Энергия: {old_energy} → {player.energy}/100\n\n"
        f"💰 Оплата: {price_text}\n"
        f"   Осталось денег: {new_money:,} руб.\n\n"
        f"📊 Всего лечений: {new_treatment_count}"
    )

    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def handle_heal(player, vk, user_id: int):
    """Лечиться в больнице

    Ценообразование:
      - 1-е лечение: бесплатно (помощь новичкам)
      - 2+ лечение: фактический объём помощи + мягкие надбавки уровня/ранга
      - цена ограничена персональным потолком текущего ранга
    """
    from main import create_location_keyboard
    from infra import database

    if player.current_location_id == "больница":
        user_data = database.get_user_by_vk(user_id)
        treatment_count = user_data.get('hospital_treatments', 0) if user_data else 0
        old_hp = int(player.health)
        old_energy = int(player.energy)
        missing_hp = max(0, int(player.max_health) - old_hp)
        missing_energy = max(0, 100 - old_energy)

        if missing_hp <= 0 and missing_energy <= 0:
            database.clear_runtime_state(user_id, HEAL_QUOTE_RUNTIME_KEY)
            vk.messages.send(
                user_id=user_id,
                message=(
                    "🏥 Врач осмотрел тебя и убрал инструменты.\n\n"
                    "Серьёзной помощи не требуется: здоровье и энергия уже в норме."
                ),
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
            return

        rank_tier, rank_name, rank_min_level = _get_player_rank_info(player)
        price_info = calculate_hospital_treatment_price(
            player_level=player.level,
            rank_tier=rank_tier,
            missing_hp=missing_hp,
            missing_energy=missing_energy,
            treatment_count=treatment_count,
            rank_min_level=rank_min_level,
        )
        price = int(price_info["price"])
        passive = player._get_passive_bonuses() if hasattr(player, "_get_passive_bonuses") else {}
        hospital_discount_pct = max(0, min(80, int(passive.get("hospital_price_discount_pct", 0) or 0)))
        if hospital_discount_pct > 0 and price > 0:
            price = max(0, int(price * (100 - hospital_discount_pct) / 100))

        # Показываем точную цену до лечения. Подтверждение отдельной кнопкой.
        if price > 0:
            _set_pending_heal_quote(
                user_id=user_id,
                price=price,
                missing_hp=missing_hp,
                missing_energy=missing_energy,
                level=int(player.level),
                rank_tier=int(rank_tier),
            )
            discount_line = (
                f"\nСкидка класса: -{hospital_discount_pct}%." if hospital_discount_pct > 0 else ""
            )
            vk.messages.send(
                user_id=user_id,
                message=(
                    "🏥 Предварительный счёт за лечение:\n\n"
                    f"💸 Стоимость: {price:,} руб.\n"
                    f"❤️ Восстановление HP: +{missing_hp}\n"
                    f"⚡ Восстановление энергии: +{missing_energy}\n"
                    f"🏅 Ранг: {rank_name}\n"
                    f"📈 Уровень: {player.level}\n"
                    f"📉 Потолок ранга: {price_info['cap']:,} руб."
                    f"{discount_line}\n\n"
                    "Нажми кнопку 'Подтвердить лечение' в течение 2 минут.\n"
                    "Если передумал, нажми 'Отмена лечения'."
                ),
                keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
                random_id=0
            )
            return

        database.clear_runtime_state(user_id, HEAL_QUOTE_RUNTIME_KEY)
        _execute_hospital_heal(
            player,
            vk,
            user_id,
            price=price,
            price_info=price_info,
            rank_name=rank_name,
            hospital_discount_pct=hospital_discount_pct,
            old_hp=old_hp,
            old_energy=old_energy,
            missing_hp=missing_hp,
            missing_energy=missing_energy,
            treatment_count=treatment_count,
        )
    else:
        database.clear_runtime_state(user_id, HEAL_QUOTE_RUNTIME_KEY)
        vk.messages.send(
            user_id=user_id,
            message="Лечение доступно только в Больнице.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )


def handle_confirm_heal(player, vk, user_id: int):
    """Подтверждение заранее рассчитанного лечения в больнице."""
    from main import create_location_keyboard

    if player.current_location_id != "больница":
        database.clear_runtime_state(user_id, HEAL_QUOTE_RUNTIME_KEY)
        vk.messages.send(
            user_id=user_id,
            message="Подтверждение лечения доступно только в Больнице.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    pending = _get_pending_heal_quote(user_id)
    if not pending:
        vk.messages.send(
            user_id=user_id,
            message="Нет активного счёта. Сначала нажми 'Лечиться'.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    user_data = database.get_user_by_vk(user_id)
    treatment_count = user_data.get('hospital_treatments', 0) if user_data else 0
    old_hp = int(player.health)
    old_energy = int(player.energy)
    missing_hp = max(0, int(player.max_health) - old_hp)
    missing_energy = max(0, 100 - old_energy)

    if missing_hp <= 0 and missing_energy <= 0:
        database.clear_runtime_state(user_id, HEAL_QUOTE_RUNTIME_KEY)
        vk.messages.send(
            user_id=user_id,
            message="Лечение уже не требуется: здоровье и энергия в норме.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    rank_tier, rank_name, rank_min_level = _get_player_rank_info(player)
    price_info = calculate_hospital_treatment_price(
        player_level=player.level,
        rank_tier=rank_tier,
        missing_hp=missing_hp,
        missing_energy=missing_energy,
        treatment_count=treatment_count,
        rank_min_level=rank_min_level,
    )
    price = int(price_info["price"])
    passive = player._get_passive_bonuses() if hasattr(player, "_get_passive_bonuses") else {}
    hospital_discount_pct = max(0, min(80, int(passive.get("hospital_price_discount_pct", 0) or 0)))
    if hospital_discount_pct > 0 and price > 0:
        price = max(0, int(price * (100 - hospital_discount_pct) / 100))

    matches_pending = bool(
        int(pending.get("price", -1)) == price
        and int(pending.get("missing_hp", -1)) == missing_hp
        and int(pending.get("missing_energy", -1)) == missing_energy
        and int(pending.get("level", -1)) == int(player.level)
        and int(pending.get("rank_tier", -1)) == int(rank_tier)
    )
    if not matches_pending:
        _set_pending_heal_quote(
            user_id=user_id,
            price=price,
            missing_hp=missing_hp,
            missing_energy=missing_energy,
            level=int(player.level),
            rank_tier=int(rank_tier),
        )
        vk.messages.send(
            user_id=user_id,
            message=(
                "Счёт изменился, потому что параметры персонажа обновились.\n"
                "Нажми 'Лечиться' чтобы посмотреть новый расчёт, затем подтверди."
            ),
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    database.clear_runtime_state(user_id, HEAL_QUOTE_RUNTIME_KEY)
    _execute_hospital_heal(
        player,
        vk,
        user_id,
        price=price,
        price_info=price_info,
        rank_name=rank_name,
        hospital_discount_pct=hospital_discount_pct,
        old_hp=old_hp,
        old_energy=old_energy,
        missing_hp=missing_hp,
        missing_energy=missing_energy,
        treatment_count=treatment_count,
    )


def handle_cancel_heal(player, vk, user_id: int):
    """Отменить предварительный счёт лечения."""
    from main import create_location_keyboard

    pending = _get_pending_heal_quote(user_id)
    if not pending:
        vk.messages.send(
            user_id=user_id,
            message="Активного счёта на лечение нет.",
            keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
            random_id=0
        )
        return

    database.clear_runtime_state(user_id, HEAL_QUOTE_RUNTIME_KEY)
    vk.messages.send(
        user_id=user_id,
        message="❎ Лечение отменено. Деньги не списаны.",
        keyboard=create_location_keyboard(player.current_location_id).get_keyboard(),
        random_id=0
    )


def get_status(player, vk, user_id: int):
    """Показать статус персонажа"""
    from infra.state_manager import try_edit_or_send
    try_edit_or_send(
        vk, user_id,
        message=player.get_status(),
    )


def show_welcome(vk, user_id: int):
    """Показать приветственное сообщение"""
    from handlers.keyboards import create_main_keyboard, create_location_keyboard
    from infra.state_manager import set_ui_screen
    from handlers.commands import get_welcome_message
    from models.locations import get_location
    from infra import database, config

    # Проверяем, новый ли игрок
    user_data = database.get_user_by_vk(user_id)

    if user_data:
        # Игрок уже существует - показываем ТЕКУЩУЮ локацию, без телепорта в город.
        current_location = user_data.get("location") or "город"
        loc = get_location(current_location) or get_location("город")
        player_level = user_data.get('level', 0)
        _send_location_message(
            vk,
            user_id,
            loc.id,
            (
                f"{loc.name}\n\n{loc.description}\n\n"
                "Черный рынок доступен с первого уровня.\n"
                f"P2P рынок игроков на Черном рынке доступен с {config.MARKET_MIN_LEVEL} уровня."
            ),
            create_location_keyboard(current_location, player_level).get_keyboard(),
        )
        set_ui_screen(user_id, {"name": "location"}, clear_stack=True)
    else:
        # Новый игрок - показываем приветствие
        vk.messages.send(
            user_id=user_id,
            message=get_welcome_message(),
            keyboard=create_main_keyboard().get_keyboard(),
            random_id=0
        )
        set_ui_screen(user_id, {"name": "location"}, clear_stack=True)
