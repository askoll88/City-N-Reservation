"""
Модуль управления состоянием бота
Централизованное хранение состояний игроков, боев, диалогов
"""
from __future__ import annotations
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

class LockedDict:
    """Потокобезопасный dict с минимальным API, совместимым с текущим кодом."""

    def __init__(self):
        self._data = {}
        self._lock = threading.RLock()

    def __contains__(self, key):
        with self._lock:
            return key in self._data

    def __getitem__(self, key):
        with self._lock:
            return self._data[key]

    def __setitem__(self, key, value):
        with self._lock:
            self._data[key] = value

    def __delitem__(self, key):
        with self._lock:
            del self._data[key]

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def pop(self, key, default=None):
        with self._lock:
            return self._data.pop(key, default)

    def clear(self):
        with self._lock:
            self._data.clear()

    def keys(self):
        with self._lock:
            return list(self._data.keys())

    def items(self):
        with self._lock:
            return list(self._data.items())

    def update(self, key, func):
        """Атомарно прочитать, модифицировать и записать значение.

        func получает текущее значение (или default если ключа нет)
        и должен вернуть новое значение.
        """
        with self._lock:
            value = self._data.get(key)
            self._data[key] = func(value)

    def __len__(self):
        with self._lock:
            return len(self._data)


# === Глобальное состояние ===
_combat_state = LockedDict()  # {user_id: combat_data}
_dialog_state = LockedDict()  # {user_id: {"npc": str, "stage": str}}
_research_state = LockedDict()  # {user_id: research_data}
_anomaly_state = LockedDict()  # {user_id: anomaly_data}
_pending_purchase_state = LockedDict()  # {user_id: purchase_data}
_pending_loot_choice_state = LockedDict()  # {user_id: loot_choice_data}
_pending_emission_risk_exit_state = LockedDict()  # {user_id: risk_exit_data}
_travel_state = LockedDict()  # {user_id: travel_data}
_ui_state = LockedDict()  # {user_id: {"current": dict, "stack": [dict, ...]}}
_runtime_loaded = LockedDict()  # {user_id: {"loaded_at": ts}}

_RUNTIME_KEY_DIALOG = "dialog_state"
_RUNTIME_KEY_TRAVEL = "travel_state"
_RUNTIME_KEY_UI = "ui_state"

# Кэш игроков
_players_cache = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 60  # Время жизни кэша в секундах
_MAX_CACHE_SIZE = 100


def get_combat_state() -> dict:
    """Получить состояние боев (для импорта)"""
    return _combat_state


def _persist_runtime_state(user_id: int, state_key: str, payload: dict):
    """Сохранить runtime-состояние в БД (fail-safe)."""
    try:
        import database
        database.set_runtime_state(user_id, state_key, payload or {})
    except Exception:
        logger.exception("Не удалось сохранить runtime state: user_id=%s key=%s", user_id, state_key)


def _clear_runtime_state(user_id: int, state_key: str):
    """Удалить runtime-состояние из БД (fail-safe)."""
    try:
        import database
        database.clear_runtime_state(user_id, state_key)
    except Exception:
        logger.exception("Не удалось очистить runtime state: user_id=%s key=%s", user_id, state_key)


def get_dialog_state() -> dict:
    """Получить состояние диалогов (для импорта)"""
    return _dialog_state


def get_research_state() -> dict:
    """Получить состояние исследований"""
    return _research_state


def get_anomaly_state() -> dict:
    """Получить состояние аномалий"""
    return _anomaly_state


# === Работа с состоянием боя ===

def is_in_combat(user_id: int) -> bool:
    """Проверить, находится ли игрок в бою"""
    return user_id in _combat_state


def set_combat_state(user_id: int, data: dict):
    """Установить состояние боя для игрока"""
    _combat_state[user_id] = data


def get_combat_data(user_id: int) -> dict:
    """Получить данные боя игрока"""
    return _combat_state.get(user_id)


def clear_combat_state(user_id: int):
    """Очистить состояние боя"""
    _combat_state.pop(user_id, None)


# === Работа с диалогами ===

def is_in_dialog(user_id: int) -> bool:
    """Проверить, находится ли игрок в диалоге"""
    return user_id in _dialog_state


def set_dialog_state(user_id: int, npc_id: str, stage: str = "menu"):
    """Установить состояние диалога"""
    payload = {"npc": npc_id, "stage": stage}
    _dialog_state[user_id] = payload
    _persist_runtime_state(user_id, _RUNTIME_KEY_DIALOG, payload)


def get_dialog_info(user_id: int) -> dict:
    """Получить информацию о диалоге"""
    return _dialog_state.get(user_id)


def clear_dialog_state(user_id: int):
    """Очистить состояние диалога"""
    _dialog_state.pop(user_id, None)
    _clear_runtime_state(user_id, _RUNTIME_KEY_DIALOG)


# === Работа с исследованиями ===

def is_researching(user_id: int) -> bool:
    """Проверить, исследует ли игрок"""
    return user_id in _research_state


def set_research_state(user_id: int, data: dict):
    """Установить состояние исследования"""
    _research_state[user_id] = {
        **data,
        "start_time": time.time()
    }


def get_research_data(user_id: int) -> dict:
    """Получить данные исследования"""
    return _research_state.get(user_id)


def clear_research_state(user_id: int):
    """Очистить состояние исследования"""
    _research_state.pop(user_id, None)


# === Работа с аномалиями ===

def is_in_anomaly(user_id: int) -> bool:
    """Проверить, находится ли игрок в аномалии"""
    return user_id in _anomaly_state


def set_anomaly_state(user_id: int, data: dict):
    """Установить состояние аномалии"""
    _anomaly_state[user_id] = data


def get_anomaly_data(user_id: int) -> dict:
    """Получить данные аномалии"""
    return _anomaly_state.get(user_id)


def clear_anomaly_state(user_id: int):
    """Очистить состояние аномалии"""
    _anomaly_state.pop(user_id, None)


# === Работа с исследованиями (дополнительные функции) ===

def get_research_status(user_id: int) -> dict:
    """Получить статус исследования"""
    data = _research_state.get(user_id)
    if not data:
        return None

    import time
    remaining = int(data.get('duration', 0) - (time.time() - data.get('start_time', 0)))
    return {
        'remaining': max(0, remaining),
        'location_id': data.get('location_id'),
        'start_time': data.get('start_time'),
    }


def cancel_research(user_id: int) -> bool:
    """Отменить исследование"""
    if user_id in _research_state:
        del _research_state[user_id]
        return True
    return False


# === Управление кэшем игроков ===

def cache_player(user_id: int, player: Any):
    """Кэшировать игрока"""
    global _players_cache

    with _cache_lock:
        current_time = time.time()
        
        # Очистка старых записей если кэш переполнен
        if len(_players_cache) >= _MAX_CACHE_SIZE:
            # Удаляем oldest записи
            sorted_cache = sorted(
                _players_cache.items(),
                key=lambda x: x[1].get('_timestamp', 0)
            )
            to_remove = sorted_cache[:_MAX_CACHE_SIZE // 4]  # Удаляем 25%
            for key, _ in to_remove:
                del _players_cache[key]

        _players_cache[user_id] = {
            '_player': player,
            '_timestamp': current_time
        }


def get_cached_player(user_id: int) -> Any:
    """Получить кэшированного игрока"""
    with _cache_lock:
        cached = _players_cache.get(user_id)
        if cached and (time.time() - cached['_timestamp']) < _CACHE_TTL:
            return cached['_player']
    return None


def invalidate_player_cache(user_id: int = None):
    """Инвалидировать кэш игрока"""
    global _players_cache

    with _cache_lock:
        if user_id:
            _players_cache.pop(user_id, None)
        else:
            _players_cache.clear()


def get_cached_players_count() -> int:
    """Получить количество кэшированных игроков"""
    return len(_players_cache)


# === Очистка неактивных состояний ===

def cleanup_inactive_states(max_idle_seconds: int = 300):
    """Очистить состояния неактивных игроков"""
    current_time = time.time()
    removed = 0

    # Очистка исследований
    for user_id in list(_research_state.keys()):
        data = _research_state.get(user_id)
        if data and (current_time - data.get('start_time', 0)) > max_idle_seconds:
            del _research_state[user_id]
            removed += 1

    # Очистка боев (если слишком долго)
    for user_id in list(_combat_state.keys()):
        data = _combat_state.get(user_id)
        if data and (current_time - data.get('start_time', current_time)) > max_idle_seconds:
            del _combat_state[user_id]
            removed += 1

    # Очистка pending покупок (если слишком долго)
    for user_id in list(_pending_purchase_state.keys()):
        data = _pending_purchase_state.get(user_id)
        if data and (current_time - data.get('start_time', current_time)) > max_idle_seconds:
            del _pending_purchase_state[user_id]
            removed += 1

    # Очистка pending выбора лута (если слишком долго)
    for user_id in list(_pending_loot_choice_state.keys()):
        data = _pending_loot_choice_state.get(user_id)
        if data and (current_time - data.get('created_at', current_time)) > max_idle_seconds:
            del _pending_loot_choice_state[user_id]
            removed += 1

    # Очистка pending подтверждения риска выброса (если слишком долго)
    for user_id in list(_pending_emission_risk_exit_state.keys()):
        data = _pending_emission_risk_exit_state.get(user_id)
        if data and (current_time - data.get('created_at', current_time)) > max_idle_seconds:
            del _pending_emission_risk_exit_state[user_id]
            removed += 1

    return removed


# === Работа с подтверждением покупки на рынке ===

def has_pending_purchase(user_id: int) -> bool:
    """Проверить, есть ли ожидающая подтверждения покупка"""
    return user_id in _pending_purchase_state


def set_pending_purchase(user_id: int, data: dict):
    """Установить состояние ожидающей покупки"""
    _pending_purchase_state[user_id] = {
        **data,
        "start_time": time.time()
    }


def get_pending_purchase(user_id: int) -> dict | None:
    """Получить данные ожидающей покупки"""
    return _pending_purchase_state.get(user_id)


def clear_pending_purchase(user_id: int):
    """Очистить состояние ожидающей покупки"""
    _pending_purchase_state.pop(user_id, None)


def has_pending_loot_choice(user_id: int) -> bool:
    """Проверить, есть ли ожидающий выбор найденного лута"""
    return user_id in _pending_loot_choice_state


def set_pending_loot_choice(user_id: int, data: dict):
    """Установить состояние ожидающего выбора найденного лута"""
    _pending_loot_choice_state[user_id] = {
        **data,
        "created_at": time.time()
    }


def get_pending_loot_choice(user_id: int) -> dict | None:
    """Получить данные ожидающего выбора найденного лута"""
    return _pending_loot_choice_state.get(user_id)


def clear_pending_loot_choice(user_id: int):
    """Очистить состояние ожидающего выбора найденного лута"""
    _pending_loot_choice_state.pop(user_id, None)


def has_pending_emission_risk_exit(user_id: int) -> bool:
    """Проверить, есть ли ожидающее подтверждение выхода из safe в impact."""
    return user_id in _pending_emission_risk_exit_state


def set_pending_emission_risk_exit(user_id: int, data: dict):
    """Установить ожидающее подтверждение риска выхода из safe."""
    _pending_emission_risk_exit_state[user_id] = {
        **data,
        "created_at": time.time(),
    }


def get_pending_emission_risk_exit(user_id: int) -> dict | None:
    """Получить данные ожидающего подтверждения риска выхода из safe."""
    return _pending_emission_risk_exit_state.get(user_id)


def clear_pending_emission_risk_exit(user_id: int):
    """Очистить ожидающее подтверждение риска выхода из safe."""
    _pending_emission_risk_exit_state.pop(user_id, None)


# === Работа с состоянием перемещения (travel corridor) ===

def has_travel_state(user_id: int) -> bool:
    """Проверить, находится ли игрок в коридоре перехода."""
    return user_id in _travel_state


def set_travel_state(user_id: int, data: dict):
    """Установить состояние перемещения."""
    payload = {
        **data,
        "created_at": time.time(),
    }
    _travel_state[user_id] = payload
    _persist_runtime_state(user_id, _RUNTIME_KEY_TRAVEL, payload)


def get_travel_data(user_id: int) -> dict | None:
    """Получить данные перемещения."""
    return _travel_state.get(user_id)


def update_travel_data(user_id: int, patch: dict) -> dict | None:
    """Атомарно обновить состояние перемещения и вернуть новое значение."""
    def updater(current):
        if not current:
            return None
        current.update(patch)
        return current
    _travel_state.update(user_id, updater)
    updated = _travel_state.get(user_id)
    if updated:
        _persist_runtime_state(user_id, _RUNTIME_KEY_TRAVEL, updated)
    return updated


def clear_travel_state(user_id: int):
    """Очистить состояние перемещения."""
    _travel_state.pop(user_id, None)
    _clear_runtime_state(user_id, _RUNTIME_KEY_TRAVEL)


def get_all_travel_states() -> list[tuple[int, dict]]:
    """Снимок всех активных перемещений."""
    return _travel_state.items()


# === UI Навигация (стек экранов) ===

def get_ui_state(user_id: int) -> dict:
    """Получить UI-состояние пользователя."""
    state = _ui_state.get(user_id)
    if not state:
        return {"current": {"name": "location"}, "stack": []}
    return state


def get_ui_current_screen(user_id: int) -> dict:
    """Текущий экран интерфейса."""
    state = get_ui_state(user_id)
    return state.get("current", {"name": "location"})


def set_ui_screen(user_id: int, screen: dict, push_current: bool = False, clear_stack: bool = False):
    """Установить экран интерфейса."""
    def updater(current):
        current = current or {"current": {"name": "location"}, "stack": []}
        stack = list(current.get("stack", []))
        if clear_stack:
            stack = []
        if push_current:
            prev = current.get("current")
            if prev:
                stack.append(prev)
        return {"current": dict(screen or {"name": "location"}), "stack": stack}
    _ui_state.update(user_id, updater)
    _persist_runtime_state(user_id, _RUNTIME_KEY_UI, get_ui_state(user_id))


def pop_ui_screen(user_id: int) -> dict | None:
    """Вернуться к предыдущему экрану из стека."""
    popped = {"value": None}

    def updater(current):
        current = current or {"current": {"name": "location"}, "stack": []}
        stack = list(current.get("stack", []))
        if not stack:
            popped["value"] = None
            return current
        prev = stack.pop()
        popped["value"] = prev
        return {"current": prev, "stack": stack}

    _ui_state.update(user_id, updater)
    _persist_runtime_state(user_id, _RUNTIME_KEY_UI, get_ui_state(user_id))
    return popped["value"]


def ensure_runtime_state_loaded(user_id: int):
    """
    Ленивая загрузка runtime-состояний пользователя из БД.
    Нужна после рестартов, т.к. in-memory словари пустые.
    """
    if user_id in _runtime_loaded:
        return

    try:
        import database

        if user_id not in _dialog_state:
            dialog = database.get_runtime_state(user_id, _RUNTIME_KEY_DIALOG)
            if isinstance(dialog, dict) and dialog.get("npc"):
                _dialog_state[user_id] = {
                    "npc": str(dialog.get("npc")),
                    "stage": str(dialog.get("stage") or "menu"),
                }

        if user_id not in _travel_state:
            travel = database.get_runtime_state(user_id, _RUNTIME_KEY_TRAVEL)
            if isinstance(travel, dict):
                required = {"from_location", "to_location", "start_time", "duration"}
                if required.issubset(set(travel.keys())):
                    _travel_state[user_id] = dict(travel)

        if user_id not in _ui_state:
            ui = database.get_runtime_state(user_id, _RUNTIME_KEY_UI)
            if isinstance(ui, dict):
                current = ui.get("current") or {"name": "location"}
                stack = ui.get("stack") or []
                if isinstance(current, dict) and isinstance(stack, list):
                    _ui_state[user_id] = {"current": current, "stack": stack}
    except Exception:
        logger.exception("Не удалось восстановить runtime state: user_id=%s", user_id)
    finally:
        _runtime_loaded[user_id] = {"loaded_at": time.time()}


def hydrate_travel_states_from_runtime() -> int:
    """
    Предзагрузить все активные travel-state из БД при старте процесса.
    Возвращает число восстановленных переходов.
    """
    restored = 0
    try:
        import database
        rows = database.get_all_runtime_states(_RUNTIME_KEY_TRAVEL)
        for row in rows:
            try:
                uid = int(row.get("vk_id"))
                payload = row.get("payload") or {}
                required = {"from_location", "to_location", "start_time", "duration"}
                if not isinstance(payload, dict) or not required.issubset(set(payload.keys())):
                    continue
                _travel_state[uid] = dict(payload)
                _runtime_loaded[uid] = {"loaded_at": time.time()}
                restored += 1
            except Exception:
                continue
    except Exception:
        logger.exception("Не удалось предзагрузить travel-state из runtime storage")
    return restored


# === Состояние просмотра рынка (пагинация, фильтры, сортировка) ===
_market_browse_state = LockedDict()  # {user_id: {category, page, sort, search, view}}


def set_market_browse_state(user_id: int, category: str | None = None, page: int = 1,
                              sort: str = "newest", search: str | None = None,
                              view: str = "all"):
    """Установить состояние просмотра рынка."""
    _market_browse_state[user_id] = {
        "category": category,
        "page": page,
        "sort": sort,
        "search": search,
        "view": view,
    }


def get_market_browse_state(user_id: int) -> dict | None:
    """Получить состояние просмотра рынка."""
    return _market_browse_state.get(user_id)


def clear_market_browse_state(user_id: int):
    """Очистить состояние просмотра рынка."""
    _market_browse_state.pop(user_id, None)


def set_market_my_listings_page(user_id: int, page: int = 1, status: str = "active"):
    """Атомарно обновить страницу и статус своих лотов."""
    def updater(state):
        state = state or {}
        state["my_listings_page"] = page
        state["my_listings_status"] = status
        return state
    _market_browse_state.update(user_id, updater)


def get_market_my_listings_page(user_id: int) -> tuple:
    """Получить страницу и статус для своих лотов."""
    state = _market_browse_state.get(user_id, {})
    return state.get("my_listings_page", 1), state.get("my_listings_status", "active")


# === Работа со случайными событиями ===
_pending_event_state = LockedDict()  # {user_id: event_data}


def has_pending_event(user_id: int) -> bool:
    """Проверить, есть ли ожидающее случайное событие"""
    return user_id in _pending_event_state


def set_pending_event(user_id: int, event: dict):
    """Установить состояние случайного события"""
    _pending_event_state[user_id] = event


def get_pending_event(user_id: int) -> dict | None:
    """Получить данные случайного события"""
    return _pending_event_state.get(user_id)


def clear_pending_event(user_id: int):
    """Очистить состояние случайного события"""
    _pending_event_state.pop(user_id, None)


# === Работа с состоянием выброса (Emission) ===
_emission_pending_state = LockedDict()  # {user_id: emission_event_data}


def has_emission_pending(user_id: int) -> bool:
    """Проверить, есть ли ожидающее событие выброса"""
    return user_id in _emission_pending_state


def set_emission_pending(user_id: int, data: dict):
    """Установить ожидающее событие выброса"""
    _emission_pending_state[user_id] = data


def get_emission_pending(user_id: int) -> dict | None:
    """Получить ожидающее событие выброса"""
    return _emission_pending_state.get(user_id)


def clear_emission_pending(user_id: int):
    """Очистить ожидающее событие выброса"""
    _emission_pending_state.pop(user_id, None)


# === Редактирование последнего сообщения ===
_last_message_state = LockedDict()  # {user_id: {"msg_id": int, "peer_id": int}}


def get_last_message(user_id: int) -> dict | None:
    """Получить последнее отправленное сообщение пользователя"""
    return _last_message_state.get(user_id)


def set_last_message(user_id: int, msg_id: int, peer_id: int = None):
    """Запомнить последнее сообщение для редактирования"""
    _last_message_state[user_id] = {
        "msg_id": msg_id,
        "peer_id": peer_id,
    }


def clear_last_message(user_id: int):
    """Очистить последнее сообщение"""
    _last_message_state.pop(user_id, None)


def try_edit_or_send(vk, user_id: int, message: str, keyboard=None):
    """
    Попытаться редактировать последнее сообщение.
    Если не удалось — отправить новое.
    """
    last_msg = get_last_message(user_id)
    kwargs = {"message": message}
    if keyboard:
        kwargs["keyboard"] = keyboard.get_keyboard() if hasattr(keyboard, "get_keyboard") else keyboard

    if last_msg and last_msg.get("msg_id"):
        try:
            vk.messages.edit(
                conversation_message_id=last_msg["msg_id"],
                **kwargs,
            )
            return  # Успешно отредактировано
        except Exception:
            pass

    # Fallback: отправить новое
    kwargs["random_id"] = 0
    try:
        msg_id = vk.messages.send(user_id=user_id, **kwargs)
        set_last_message(user_id, msg_id)
    except Exception:
        pass
