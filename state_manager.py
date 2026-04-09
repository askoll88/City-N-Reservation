"""
Модуль управления состоянием бота
Централизованное хранение состояний игроков, боев, диалогов
"""
import threading
import time
from typing import Any

# === Глобальное состояние ===
_combat_state = {}  # {user_id: combat_data}
_dialog_state = {}  # {user_id: {"npc": str, "stage": str}}
_research_state = {}  # {user_id: research_data}
_anomaly_state = {}  # {user_id: anomaly_data}

# Кэш игроков
_players_cache = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 60  # Время жизни кэша в секундах
_MAX_CACHE_SIZE = 100


def get_combat_state() -> dict:
    """Получить состояние боев (для импорта)"""
    return _combat_state


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
    _dialog_state[user_id] = {"npc": npc_id, "stage": stage}


def get_dialog_info(user_id: int) -> dict:
    """Получить информацию о диалоге"""
    return _dialog_state.get(user_id)


def clear_dialog_state(user_id: int):
    """Очистить состояние диалога"""
    _dialog_state.pop(user_id, None)


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

    return removed
