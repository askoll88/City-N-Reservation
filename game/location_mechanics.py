"""
Механики локаций — уникальные свойства каждой исследовательской зоны
"""
from __future__ import annotations
import random
from infra import database
from game.constants import RESEARCH_LOCATIONS

# =========================================================================
# Модификаторы локаций
# =========================================================================

LOCATION_MODIFIERS = {
    "дорога_военная_часть": {
        "name": "Военная дорога",
        "emoji": "🎖️",
        "description": "Тактическая зона — остатки военной техники и укреплений",

        # Пассивные модификаторы
        "energy_cost_mult": 1.08,      # +8% энергии (военные укрепления)
        "find_chance_mult": 1.0,       # базовый шанс находок
        "danger_mult": 1.06,           # +6% опасности
        "radiation_mult": 1.0,         # нормальная радиация
        "loot_quality": "military",    # тип лута

        # Пул аномалий (с весами)
        "anomaly_weights": {
            "жарка": 20,
            "электра": 40,             # больше электромагнитных (остатки техники)
            "воронка": 10,
            "туман": 10,
            "магнит": 40,              # больше магнитных (военное оборудование)
        },

        # Пул событий (множители к весам из RESEARCH_EVENTS)
        "event_weights": {
            "mutant": 0.85,            # меньше мутантов
            "bandit": 1.2,             # больше бандитов (мародёры)
            "military": 1.35,          # больше военных
            "artifact": 0.9,           # чуть меньше артефактов
            "stash": 1.2,              # больше тайников (военные схроны)
            "trap": 1.25,              # больше ловушек (мины, растяжки)
            "military_cache": 1.55,    # больше армейских ящиков
            "field_lab_data": 0.8,     # реже научные данные
        },

        # Уникальная механика: Засада
        "unique_mechanic": "ambush",
        "ambush_chance": 0.07,         # 7% шанс засады при исследовании
    },
    "военная_часть": {
        "name": "Военная часть",
        "emoji": "🏢",
        "description": "Внутренний периметр — казармы, склады и закрытые посты",
        "energy_cost_mult": 1.16,
        "find_chance_mult": 1.12,
        "danger_mult": 1.22,
        "radiation_mult": 1.02,
        "loot_quality": "military",
        "anomaly_weights": {
            "жарка": 18,
            "электра": 45,
            "воронка": 10,
            "туман": 8,
            "магнит": 48,
        },
        "event_weights": {
            "mutant": 0.75,
            "bandit": 1.05,
            "military": 1.65,
            "artifact": 0.85,
            "armory_locker": 1.7,
            "garrison_orders": 1.25,
            "drone_alarm": 1.45,
            "live_minefield": 1.35,
        },
        "event_pool": [
            "common_item",
            "rare_item",
            "military",
            "armory_locker",
            "garrison_orders",
            "drone_alarm",
            "live_minefield",
        ],
        "unique_mechanic": "ambush",
        "ambush_chance": 0.10,
    },

    "дорога_нии": {
        "name": "НИИ",
        "emoji": "🔬",
        "description": "Зона аномальной активности — лабораторные эксперименты вышли из-под контроля",

        # Пассивные модификаторы
        "energy_cost_mult": 1.0,       # нормальная энергия
        "find_chance_mult": 1.12,      # +12% шанс найти что-то
        "danger_mult": 1.0,            # нормальная опасность
        "radiation_mult": 1.1,         # +10% радиация
        "loot_quality": "scientific",  # тип лута

        # Пул аномалий
        "anomaly_weights": {
            "жарка": 10,
            "электра": 25,
            "воронка": 40,             # больше гравитационных (лабораторные установки)
            "туман": 40,               # больше биохимических (химикаты)
            "магнит": 15,
        },

        # Пул событий
        "event_weights": {
            "mutant": 1.1,             # больше лабораторных мутантов
            "bandit": 0.7,             # меньше бандитов (закрытая зона)
            "military": 0.85,          # меньше военных
            "artifact": 1.2,           # +20% артефактов
            "anomaly": 1.2,            # больше аномалий
            "radiation": 1.25,         # больше радиации
            "field_lab_data": 1.65,    # основной источник данных
            "artifact_cluster": 1.25,  # больше кластеров артефактов
            "psi_echo": 1.2,           # чаще пси-эхо
        },

        # Уникальная механика: Мутация Зоны
        "unique_mechanic": "zone_mutation",
        "zone_mutation_chance": 0.07,  # 7% шанс мутации после посещения
    },
    "главный_корпус_нии": {
        "name": "Главный корпус НИИ",
        "emoji": "🏛️",
        "description": "Внутренний научный корпус — данные, реагенты и аномальные карманы",
        "energy_cost_mult": 1.08,
        "find_chance_mult": 1.20,
        "danger_mult": 1.18,
        "radiation_mult": 1.18,
        "loot_quality": "scientific",
        "anomaly_weights": {
            "жарка": 8,
            "электра": 24,
            "воронка": 48,
            "туман": 45,
            "магнит": 18,
        },
        "event_weights": {
            "mutant": 1.15,
            "artifact": 1.3,
            "anomaly": 1.45,
            "sealed_archive": 1.65,
            "specimen_vault": 1.35,
            "reactor_leak": 1.35,
            "containment_breach": 1.5,
        },
        "event_pool": [
            "common_item",
            "rare_item",
            "artifact",
            "anomaly",
            "sealed_archive",
            "specimen_vault",
            "reactor_leak",
            "containment_breach",
        ],
        "unique_mechanic": "zone_mutation",
        "zone_mutation_chance": 0.10,
    },

    "дорога_зараженный_лес": {
        "name": "Заражённый лес",
        "emoji": "☢️",
        "description": "Дикая зона мутантов — аномальная флора и фауна",

        # Пассивные модификаторы
        "energy_cost_mult": 1.1,       # +10% энергии (густой воздух, аномалии)
        "find_chance_mult": 1.08,      # +8% шанс находок
        "danger_mult": 1.15,           # +15% опасность
        "radiation_mult": 1.12,        # +12% радиация
        "loot_quality": "organic",     # тип лута

        # Пул аномалий
        "anomaly_weights": {
            "жарка": 50,               # больше термальных (биологические аномалии)
            "электра": 10,
            "воронка": 15,
            "туман": 30,               # биохимический туман
            "магнит": 5,
        },

        # Пул событий
        "event_weights": {
            "mutant": 1.35,            # больше мутантов
            "bandit": 0.75,            # меньше бандитов (боятся леса)
            "military": 0.65,          # меньше военных
            "artifact": 1.05,          # чуть больше артефактов
            "enemy": 1.15,             # общий бонус к врагам
            "anomaly": 1.1,            # немного больше аномалий
            "abandoned_camp": 1.35,    # чаще брошенные лагеря
            "blood_trail": 1.45,       # чаще следы охоты
        },

        # Уникальная механика: Охота мутантов
        "unique_mechanic": "mutant_hunt",
        "mutant_hunt_chance": 0.12,    # 12% что придёт стая после убийства
        "mutant_hunt_count": [2, 2],   # фиксированно 2 врага подряд
    },
    "зараженный_лес": {
        "name": "Заражённый лес",
        "emoji": "🌲",
        "description": "Внутренняя чаща — следы стаи, органика и мутировавшие трофеи",
        "energy_cost_mult": 1.18,
        "find_chance_mult": 1.14,
        "danger_mult": 1.28,
        "radiation_mult": 1.18,
        "loot_quality": "organic",
        "anomaly_weights": {
            "жарка": 55,
            "электра": 8,
            "воронка": 18,
            "туман": 38,
            "магнит": 5,
        },
        "event_weights": {
            "mutant": 1.65,
            "artifact": 1.15,
            "anomaly": 1.2,
            "spore_grove": 1.3,
            "brood_nest": 1.55,
            "bone_cache": 1.35,
            "pack_stalk": 1.5,
        },
        "event_pool": [
            "common_item",
            "rare_item",
            "artifact",
            "anomaly",
            "spore_grove",
            "brood_nest",
            "bone_cache",
            "pack_stalk",
        ],
        "unique_mechanic": "mutant_hunt",
        "mutant_hunt_chance": 0.15,
        "mutant_hunt_count": [2, 3],
    },
}


# =========================================================================
# Лут-таблицы по локациям
# =========================================================================

# Предметы, которые чаще встречаются в определённых локациях
LOCATION_LOOT_BIAS = {
    "дорога_военная_часть": {
        "bias_items": [
            "ПМ", "АК-74", "Бронежилет", "Баллистический шлем",
            "Тактический шлем", "Берцы", "Патрон 5.45",
        ],
        "bias_weight": 0.30,  # 30% шанс что найденный предмет — из списка
    },
    "военная_часть": {
        "bias_items": [
            "АК-74", "Бронежилет", "Баллистический шлем",
            "Тактический шлем", "Берцы", "Патрон 5.45", "Аптечка",
        ],
        "bias_weight": 0.34,
    },
    "дорога_нии": {
        "bias_items": [
            "Аптечка", "Антирад", "Детектор аномалий", "Стимулятор",
            "Бинт", "Научная аптечка", "Дозиметр",
        ],
        "bias_weight": 0.30,
    },
    "главный_корпус_нии": {
        "bias_items": [
            "Аптечка", "Антирад", "Детектор аномалий", "Стимулятор",
            "Научная аптечка", "Дозиметр", "Капля", "Слизь",
        ],
        "bias_weight": 0.34,
    },
    "дорога_зараженный_лес": {
        "bias_items": [
            "Ломоть мяса", "Капля", "Слизь", "Плёнка",
            "Антирад", "Вода",
        ],
        "bias_weight": 0.30,
    },
    "зараженный_лес": {
        "bias_items": [
            "Ломоть мяса", "Капля", "Слизь", "Плёнка",
            "Антирад", "Вода", "Бинт",
        ],
        "bias_weight": 0.34,
    },
}


# =========================================================================
# Региональные gameplay loops
# =========================================================================

REGION_LOOP_FLAG_PREFIX = "region_loop"

REGION_GAMEPLAY_LOOPS = {
    "дорога_военная_часть": {
        "name": "Тревога патрулей",
        "field": "alert",
        "max": 100,
        "event_deltas": {
            "military": 18,
            "trap": 12,
            "bandit": 8,
            "mutant": 5,
            "military_cache": -16,
            "stash": -10,
            "survivor": -6,
            "nothing": -4,
        },
        "pressure_weights": {
            "military": 0.006,
            "trap": 0.003,
            "military_cache": 0.002,
        },
        "force_threshold": 85,
    },
    "военная_часть": {
        "name": "Тревога гарнизона",
        "field": "alert",
        "max": 100,
        "event_deltas": {
            "military": 22,
            "trap": 14,
            "bandit": 8,
            "mutant": 6,
            "drone_alarm": 20,
            "live_minefield": 16,
            "armory_locker": -14,
            "garrison_orders": -10,
            "survivor": -6,
            "nothing": -3,
        },
        "pressure_weights": {
            "military": 0.007,
            "drone_alarm": 0.006,
            "live_minefield": 0.004,
            "armory_locker": 0.002,
        },
        "force_threshold": 82,
    },
    "дорога_нии": {
        "name": "Нестабильность НИИ",
        "field": "instability",
        "secondary_field": "data",
        "max": 100,
        "event_deltas": {
            "anomaly": 18,
            "radiation": 14,
            "psi_echo": 16,
            "artifact_cluster": 12,
            "artifact": 8,
            "field_lab_data": -12,
            "nothing": -3,
        },
        "pressure_weights": {
            "anomaly": 0.005,
            "radiation": 0.004,
            "psi_echo": 0.003,
            "field_lab_data": 0.002,
        },
        "force_threshold": 88,
        "breakthrough_data": 3,
    },
    "главный_корпус_нии": {
        "name": "Нестабильность корпуса",
        "field": "instability",
        "secondary_field": "data",
        "max": 100,
        "event_deltas": {
            "anomaly": 22,
            "radiation": 16,
            "psi_echo": 18,
            "artifact_cluster": 14,
            "artifact": 10,
            "sealed_archive": -10,
            "specimen_vault": 10,
            "reactor_leak": 18,
            "containment_breach": 20,
            "nothing": -2,
        },
        "pressure_weights": {
            "anomaly": 0.006,
            "reactor_leak": 0.005,
            "containment_breach": 0.005,
            "sealed_archive": 0.003,
        },
        "force_threshold": 84,
        "breakthrough_data": 3,
    },
    "дорога_зараженный_лес": {
        "name": "След стаи",
        "field": "trail",
        "max": 100,
        "event_deltas": {
            "blood_trail": 20,
            "mutant": 16,
            "abandoned_camp": -14,
            "survivor": -8,
            "nothing": -4,
            "artifact": 4,
        },
        "pressure_weights": {
            "mutant": 0.006,
            "blood_trail": 0.005,
            "abandoned_camp": 0.002,
        },
        "force_threshold": 86,
    },
    "зараженный_лес": {
        "name": "Охота стаи",
        "field": "trail",
        "max": 100,
        "event_deltas": {
            "blood_trail": 24,
            "mutant": 18,
            "spore_grove": 10,
            "brood_nest": 22,
            "pack_stalk": 20,
            "bone_cache": -10,
            "survivor": -6,
            "nothing": -3,
            "artifact": 5,
        },
        "pressure_weights": {
            "mutant": 0.007,
            "brood_nest": 0.006,
            "pack_stalk": 0.006,
            "bone_cache": 0.002,
        },
        "force_threshold": 82,
    },
}


def _clamp_loop_value(value: int, max_value: int = 100) -> int:
    return max(0, min(max_value, int(value or 0)))


def _loop_flag_name(location_id: str, field: str) -> str:
    return f"{REGION_LOOP_FLAG_PREFIX}:{location_id}:{field}"


def _get_loop_value(user_id: int | None, location_id: str, field: str) -> int:
    if user_id is None:
        return 0
    try:
        return int(database.get_user_flag(int(user_id), _loop_flag_name(location_id, field), 0) or 0)
    except Exception:
        return 0


def _set_loop_value(user_id: int | None, location_id: str, field: str, value: int):
    if user_id is None:
        return
    try:
        database.set_user_flag(int(user_id), _loop_flag_name(location_id, field), int(value))
    except Exception:
        return


def get_region_loop_config(location_id: str) -> dict | None:
    """Получить описание gameplay loop для исследовательской ветки."""
    return REGION_GAMEPLAY_LOOPS.get(location_id)


def get_region_loop_state(user_id: int | None, location_id: str) -> dict:
    """Текущее состояние ветки для игрока."""
    config = get_region_loop_config(location_id)
    if not config:
        return {}

    field = config["field"]
    max_value = int(config.get("max", 100) or 100)
    state = {field: _clamp_loop_value(_get_loop_value(user_id, location_id, field), max_value)}
    secondary = config.get("secondary_field")
    if secondary:
        state[secondary] = max(0, int(_get_loop_value(user_id, location_id, secondary) or 0))
    return state


def reset_region_loop_state(user_id: int | None, location_id: str):
    """Сбросить loop-состояние ветки для игрока."""
    config = get_region_loop_config(location_id)
    if not config:
        return
    _set_loop_value(user_id, location_id, config["field"], 0)
    secondary = config.get("secondary_field")
    if secondary:
        _set_loop_value(user_id, location_id, secondary, 0)


def get_region_loop_event_weights(user_id: int | None, location_id: str) -> dict:
    """
    Динамические множители событий от состояния ветки.

    Это делает следующие исследования зависимыми от предыдущих: накопленная
    тревога чаще приводит к патрулям, нестабильность — к аномалиям, следы — к
    охоте.
    """
    config = get_region_loop_config(location_id)
    if not config:
        return {}

    state = get_region_loop_state(user_id, location_id)
    pressure = state.get(config["field"], 0)
    if pressure <= 0:
        return {}

    weights = {}
    for event_id, per_point in config.get("pressure_weights", {}).items():
        weights[event_id] = 1.0 + min(0.75, pressure * float(per_point or 0))
    return weights


def apply_region_loop_event(user_id: int | None, location_id: str, event_id: str) -> dict:
    """
    Применить событие исследования к loop-состоянию региона.

    Возвращает эффекты для обработчика боя/исследования:
    - messages: короткие сообщения игроку;
    - override_event: событие, которое заменяет выбранное, если давление сорвалось;
    - force_mutation / force_hunt / science_breakthrough / organic_trophy.
    """
    config = get_region_loop_config(location_id)
    if not config:
        return {"messages": [], "effects": {}, "state": {}}

    field = config["field"]
    max_value = int(config.get("max", 100) or 100)
    state = get_region_loop_state(user_id, location_id)
    before = int(state.get(field, 0) or 0)
    delta = int(config.get("event_deltas", {}).get(event_id, 2 if event_id != "nothing" else -3) or 0)
    pressure = _clamp_loop_value(before + delta, max_value)
    messages: list[str] = []
    effects: dict = {}
    override_event = None

    if config.get("field") == "alert":
        if before < 55 <= pressure:
            messages.append("📻 В эфире стало тесно: короткие военные переговоры идут чаще, патрули стягиваются к маршруту.")
        if pressure >= int(config.get("force_threshold", 85)) and event_id not in {"military"}:
            override_event = "military"
            effects["forced_ambush"] = True
            messages.append("🚨 Тревога сорвалась: сирена захлебнулась и стихла. Патруль уже перекрывает проход, назад без боя не выйти.")
            pressure = max(35, pressure - 38)

    elif config.get("field") == "instability":
        data = int(state.get("data", 0) or 0)
        if event_id in {"field_lab_data", "sealed_archive"}:
            data += 1
            messages.append(f"🧾 Накопители НИИ собраны в связный пакет: {data}/{config.get('breakthrough_data', 3)}.")
        if before < 60 <= pressure:
            messages.append("🌀 Приборы ловят всплески один за другим. Корпуса НИИ будто меняют планировку прямо за спиной.")
        if pressure >= int(config.get("force_threshold", 88)) and event_id != "anomaly":
            override_event = "anomaly"
            effects["force_mutation"] = True
            messages.append("☢️ Нестабильность сорвалась в пик: коридор впереди провалился в аномальный карман.")
            pressure = max(45, pressure - 34)
        if data >= int(config.get("breakthrough_data", 3)):
            data -= int(config.get("breakthrough_data", 3))
            pressure = max(0, pressure - 24)
            effects["science_breakthrough"] = True
            messages.append("🔬 Пакет данных полный. Учёные смогут вытащить из него не слухи, а рабочие координаты.")
        state["data"] = data
        _set_loop_value(user_id, location_id, "data", data)

    elif config.get("field") == "trail":
        if event_id in {"blood_trail", "mutant", "brood_nest", "pack_stalk"}:
            effects["organic_trophy"] = True
        if before < 55 <= pressure:
            messages.append("🐾 Следы начинают сходиться в одну дугу. Стая не случайно рядом, она ведёт маршрут.")
        if pressure >= int(config.get("force_threshold", 86)) and event_id != "mutant":
            override_event = "mutant"
            effects["force_hunt"] = True
            messages.append("🐺 Лес стих. Стая взяла след, и тихий поиск превратился в охоту.")
            pressure = max(38, pressure - 40)

    _set_loop_value(user_id, location_id, field, pressure)
    state[field] = pressure
    return {
        "messages": messages,
        "effects": effects,
        "override_event": override_event,
        "state": state,
        "delta": delta,
    }


def format_region_loop_status(user_id: int | None, location_id: str) -> str | None:
    """Короткий статус loop для UI исследования/карты."""
    config = get_region_loop_config(location_id)
    if not config:
        return None
    state = get_region_loop_state(user_id, location_id)

    if config.get("field") == "alert":
        value = state.get("alert", 0)
        label = "тихо" if value < 35 else "настороженно" if value < 70 else "тревога"
        return f"{config.get('name', 'Тревога')}: {value}/100 ({label})"
    if config.get("field") == "instability":
        value = state.get("instability", 0)
        data = state.get("data", 0)
        label = "стабильно" if value < 35 else "фонит" if value < 70 else "срыв"
        return f"{config.get('name', 'Нестабильность')}: {value}/100 ({label}), данные {data}/3"
    if config.get("field") == "trail":
        value = state.get("trail", 0)
        label = "редкие следы" if value < 35 else "стая рядом" if value < 70 else "охота"
        return f"{config.get('name', 'След стаи')}: {value}/100 ({label})"
    return None


# =========================================================================
# Зона мутации (состояние)
# =========================================================================

_zone_mutation_state = {}  # {location_id: {"active": bool, "bonus_find": float, "bonus_danger": float}}


def get_zone_mutation_state(location_id: str) -> dict:
    """Получить состояние мутации локации"""
    return _zone_mutation_state.get(location_id, {"active": False, "bonus_find": 0, "bonus_danger": 0})


def set_zone_mutation_state(location_id: str, active: bool, bonus_find: float = 0, bonus_danger: float = 0):
    """Установить состояние мутации локации"""
    _zone_mutation_state[location_id] = {
        "active": active,
        "bonus_find": bonus_find,
        "bonus_danger": bonus_danger,
    }


def clear_zone_mutation_state(location_id: str):
    """Очистить состояние мутации"""
    _zone_mutation_state.pop(location_id, None)


# =========================================================================
# API — работа с модификаторами
# =========================================================================

def get_location_modifier(location_id: str) -> dict | None:
    """Получить все модификаторы локации"""
    return LOCATION_MODIFIERS.get(location_id)


def is_research_location(location_id: str) -> bool:
    """Проверить, является ли локация исследовательской с модификаторами"""
    return location_id in LOCATION_MODIFIERS


def get_anomaly_weights(location_id: str) -> dict:
    """Получить веса аномалий для локации"""
    mod = LOCATION_MODIFIERS.get(location_id)
    if not mod:
        return None
    return mod.get("anomaly_weights")


def get_event_weights(location_id: str) -> dict:
    """Получить множители весов событий для локации"""
    mod = LOCATION_MODIFIERS.get(location_id)
    if not mod:
        return None
    weights = dict(mod.get("event_weights") or {})
    if "event_pool" in mod:
        weights["__event_pool"] = set(mod.get("event_pool") or [])
    if "required_event_tags" in mod:
        weights["__required_tags"] = set(mod.get("required_event_tags") or [])
    if "blocked_event_tags" in mod:
        weights["__blocked_tags"] = set(mod.get("blocked_event_tags") or [])
    return weights


def get_energy_cost_mult(location_id: str) -> float:
    """Получить множитель стоимости энергии"""
    mod = LOCATION_MODIFIERS.get(location_id)
    if not mod:
        return 1.0
    return mod.get("energy_cost_mult", 1.0)


def get_find_chance_mult(location_id: str) -> float:
    """Получить множитель шанса находок"""
    mod = LOCATION_MODIFIERS.get(location_id)
    if not mod:
        return 1.0

    base = mod.get("find_chance_mult", 1.0)

    # Бонус мутации Зоны (НИИ)
    if location_id in _zone_mutation_state:
        state = _zone_mutation_state[location_id]
        if state["active"]:
            base += state["bonus_find"]

    return base


def get_danger_mult(location_id: str) -> float:
    """Получить множитель опасности"""
    mod = LOCATION_MODIFIERS.get(location_id)
    if not mod:
        return 1.0

    base = mod.get("danger_mult", 1.0)

    # Бонус мутации Зоны (НИИ)
    if location_id in _zone_mutation_state:
        state = _zone_mutation_state[location_id]
        if state["active"]:
            base += state["bonus_danger"]

    return base


def get_radiation_mult(location_id: str) -> float:
    """Получить множитель радиации"""
    mod = LOCATION_MODIFIERS.get(location_id)
    if not mod:
        return 1.0
    return mod.get("radiation_mult", 1.0)


def get_loot_quality(location_id: str) -> str | None:
    """Получить тип лута локации"""
    mod = LOCATION_MODIFIERS.get(location_id)
    if not mod:
        return None
    return mod.get("loot_quality")


# =========================================================================
# Уникальные механики
# =========================================================================

def check_ambush(location_id: str, user_id: int | None = None) -> bool:
    """Проверить засаду (Военная дорога)"""
    mod = LOCATION_MODIFIERS.get(location_id)
    if not mod or mod.get("unique_mechanic") != "ambush":
        return False
    alert = get_region_loop_state(user_id, location_id).get("alert", 0) if user_id is not None else 0
    chance = float(mod.get("ambush_chance", 0) or 0) + min(0.12, alert * 0.0012)
    return random.random() < chance


def check_zone_mutation(location_id: str, user_id: int | None = None, force: bool = False) -> dict | None:
    """
    Проверить мутацию Зоны (НИИ).
    Возвращает dict с информацией о мутации или None.
    """
    mod = LOCATION_MODIFIERS.get(location_id)
    if not mod or mod.get("unique_mechanic") != "zone_mutation":
        return None

    instability = get_region_loop_state(user_id, location_id).get("instability", 0) if user_id is not None else 0
    mutation_chance = float(mod.get("zone_mutation_chance", 0) or 0) + min(0.15, instability * 0.0015)

    if force or random.random() < mutation_chance:
        # Мутация активна!
        bonus_find = random.uniform(0.1, 0.3)    # +10-30% к находкам
        bonus_danger = random.uniform(0.1, 0.25)  # +10-25% к опасности
        set_zone_mutation_state(location_id, True, bonus_find, bonus_danger)
        return {
            "active": True,
            "bonus_find": bonus_find,
            "bonus_danger": bonus_danger,
            "message": (
                "🌀 **МУТАЦИЯ ЗОНЫ!**\n\n"
                "Аномальная активность усилилась! Зона изменилась...\n"
                f"+{int(bonus_find * 100)}% к находкам, "
                f"+{int(bonus_danger * 100)}% к опасности\n\n"
                "Действует до следующего посещения НИИ."
            ),
        }

    # Если мутация была активной — сбрасываем
    if location_id in _zone_mutation_state:
        clear_zone_mutation_state(location_id)

    return None


def check_mutant_hunt(user_id: int | None = None, location_id: str = "дорога_зараженный_лес") -> bool:
    """Проверить охоту мутантов (Заражённый лес)"""
    mod = LOCATION_MODIFIERS.get(location_id)
    if not mod or mod.get("unique_mechanic") != "mutant_hunt":
        return False
    trail = (
        get_region_loop_state(user_id, location_id).get("trail", 0)
        if user_id is not None
        else 0
    )
    chance = float(mod.get("mutant_hunt_chance", 0) or 0) + min(0.14, trail * 0.0014)
    return random.random() < chance


def get_mutant_hunt_count(location_id: str = "дорога_зараженный_лес") -> int:
    """Получить количество врагов в охоте мутантов"""
    mod = LOCATION_MODIFIERS.get(location_id)
    if not mod:
        return 2
    count_range = mod.get("mutant_hunt_count", [2, 3])
    return random.randint(count_range[0], count_range[1])


# =========================================================================
# Выбор аномалии с учётом локации
# =========================================================================

def get_random_anomaly_for_location(location_id: str) -> dict:
    """Получить случайную аномалию с весами локации"""
    from game import anomalies

    weights = get_anomaly_weights(location_id)
    if not weights:
        # Без весов — равномерно
        return anomalies.get_random_anomaly()

    # Фильтруем только аномалии, которые есть в ANOMALIES
    valid_anomalies = {k: v for k, v in weights.items() if k in anomalies.ANOMALIES}

    if not valid_anomalies:
        return anomalies.get_random_anomaly()

    # weighted random selection
    anomaly_type = random.choices(
        list(valid_anomalies.keys()),
        weights=list(valid_anomalies.values()),
    )[0]

    return {
        "type": anomaly_type,
        **anomalies.ANOMALIES[anomaly_type],
    }


# =========================================================================
# Лут-бонус локации
# =========================================================================

def get_location_loot_bias(location_id: str) -> list[str]:
    """Получить список предметов с бонусом для локации"""
    bias = LOCATION_LOOT_BIAS.get(location_id)
    if not bias:
        return []
    return bias.get("bias_items", [])


def get_location_loot_bias_chance(location_id: str) -> float:
    """Получить шанс бонусного лута"""
    bias = LOCATION_LOOT_BIAS.get(location_id)
    if not bias:
        return 0
    return bias.get("bias_weight", 0)
