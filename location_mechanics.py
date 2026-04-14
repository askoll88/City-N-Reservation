"""
Механики локаций — уникальные свойства каждой исследовательской зоны
"""
import random
import database
from constants import RESEARCH_LOCATIONS

# =========================================================================
# Модификаторы локаций
# =========================================================================

LOCATION_MODIFIERS = {
    "дорога_военная_часть": {
        "name": "Военная дорога",
        "emoji": "🎖️",
        "description": "Тактическая зона — остатки военной техники и укреплений",

        # Пассивные модификаторы
        "energy_cost_mult": 1.1,       # +10% энергии (военные укрепления)
        "find_chance_mult": 1.0,       # базовый шанс находок
        "danger_mult": 1.1,            # +10% опасности
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
            "mutant": 0.7,             # меньше мутантов
            "bandit": 1.3,             # больше бандитов (мародёры)
            "military": 1.8,           # MUCH больше военных
            "artifact": 0.8,           # чуть меньше артефактов
            "stash": 1.5,              # больше тайников (военные схроны)
            "trap": 1.5,               # больше ловушек (мины, растяжки)
        },

        # Уникальная механика: Засада
        "unique_mechanic": "ambush",
        "ambush_chance": 0.12,        # 12% шанс засады при исследовании
    },

    "дорога_нии": {
        "name": "НИИ",
        "emoji": "🔬",
        "description": "Зона аномальной активности — лабораторные эксперименты вышли из-под контроля",

        # Пассивные модификаторы
        "energy_cost_mult": 1.0,       # нормальная энергия
        "find_chance_mult": 1.2,       # +20% шанс найти что-то
        "danger_mult": 1.0,            # нормальная опасность
        "radiation_mult": 1.15,        # +15% радиация
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
            "mutant": 1.2,             # больше лабораторных мутантов
            "bandit": 0.5,             # меньше бандитов (закрытая зона)
            "military": 0.7,           # меньше военных
            "artifact": 1.3,           # +30% артефактов
            "anomaly": 1.4,            # больше аномалий
            "radiation": 1.5,          # больше радиации
        },

        # Уникальная механика: Мутация Зоны
        "unique_mechanic": "zone_mutation",
        "zone_mutation_chance": 0.10,  # 10% шанс мутации после посещения
    },

    "дорога_зараженный_лес": {
        "name": "Заражённый лес",
        "emoji": "☢️",
        "description": "Дикая зона мутантов — аномальная флора и фауна",

        # Пассивные модификаторы
        "energy_cost_mult": 1.15,      # +15% энергии (густой воздух, аномалии)
        "find_chance_mult": 1.1,       # +10% шанс находок
        "danger_mult": 1.25,           # +25% опасность
        "radiation_mult": 1.2,         # +20% радиация
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
            "mutant": 1.8,             # MUCH больше мутантов
            "bandit": 0.6,             # меньше бандитов (боятся леса)
            "military": 0.5,           # меньше военных
            "artifact": 1.1,           # чуть больше артефактов
            "enemy": 1.5,              # общий бонус к врагам
        },

        # Уникальная механика: Охота мутантов
        "unique_mechanic": "mutant_hunt",
        "mutant_hunt_chance": 0.20,    # 20% что придёт стая после убийства
        "mutant_hunt_count": [2, 3],   # 2-3 врага подряд
    },
}


# =========================================================================
# Лут-таблицы по локациям
# =========================================================================

# Предметы, которые чаще встречаются в определённых локациях
LOCATION_LOOT_BIAS = {
    "дорога_военная_часть": {
        "bias_items": [
            "ПМ", "АК-74", "Бронежилет", "Кевларовый шлем",
            "Армейский бронежилет", "Военный шлем", "Патроны",
        ],
        "bias_weight": 0.30,  # 30% шанс что найденный предмет — из списка
    },
    "дорога_нии": {
        "bias_items": [
            "Аптечка", "Антирад", "Детектор аномалий", "Стимулятор",
            "Бинт", "Водка", "Научный отчёт",
        ],
        "bias_weight": 0.30,
    },
    "дорога_зараженный_лес": {
        "bias_items": [
            "Мясо мутанта", "Коготь", "Шкура", "Мутаген",
            "Зубы волка", "Глаз мутанта",
        ],
        "bias_weight": 0.30,
    },
}


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
    return mod.get("event_weights")


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

def check_ambush(location_id: str) -> bool:
    """Проверить засаду (Военная дорога)"""
    if location_id != "дорога_военная_часть":
        return False
    mod = LOCATION_MODIFIERS.get(location_id)
    if not mod:
        return False
    return random.random() < mod.get("ambush_chance", 0)


def check_zone_mutation(location_id: str) -> dict | None:
    """
    Проверить мутацию Зоны (НИИ).
    Возвращает dict с информацией о мутации или None.
    """
    if location_id != "дорога_нии":
        return None

    mod = LOCATION_MODIFIERS.get(location_id)
    if not mod:
        return None

    if random.random() < mod.get("zone_mutation_chance", 0):
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


def check_mutant_hunt() -> bool:
    """Проверить охоту мутантов (Заражённый лес)"""
    mod = LOCATION_MODIFIERS.get("дорога_зараженный_лес")
    if not mod:
        return False
    return random.random() < mod.get("mutant_hunt_chance", 0)


def get_mutant_hunt_count() -> int:
    """Получить количество врагов в охоте мутантов"""
    mod = LOCATION_MODIFIERS.get("дорога_зараженный_лес")
    if not mod:
        return 2
    count_range = mod.get("mutant_hunt_count", [2, 3])
    return random.randint(count_range[0], count_range[1])


# =========================================================================
# Выбор аномалии с учётом локации
# =========================================================================

def get_random_anomaly_for_location(location_id: str) -> dict:
    """Получить случайную аномалию с весами локации"""
    import anomalies

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
