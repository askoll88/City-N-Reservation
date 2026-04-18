"""
Система классов персонажей
Данные загружаются из БД
"""

import json
from typing import Optional


# Кэш классов в памяти
_classes_cache = None

_CLASS_ID_ALIASES = {
    "пистолетчик": "следопыт",
    "снайпер": "следопыт",
    "автоматчик": "штурмовик",
    "пулемётчик": "штурмовик",
    "пулеметчик": "штурмовик",
    "дробовик": "штурмовик",
    "боец": "охотник",
    "медик": "санитар",
    "полевой медик": "санитар",
    "сталкер": "следопыт",
    "разведчик": "следопыт",
    "sniper": "следопыт",
    "scout": "следопыт",
    "assault": "штурмовик",
    "rifleman": "штурмовик",
    "stormtrooper": "штурмовик",
    "fighter": "охотник",
    "hunter": "охотник",
    "medic": "санитар",
    "tech": "техник",
    "technician": "техник",
    "anomaly": "аномалист",
    "anomalist": "аномалист",
}


# Fallback-набор классов, если БД не содержит таблиц/функций классов.
_DEFAULT_CLASSES = {
    "следопыт": {
        "class_id": "следопыт",
        "name": "🧭 Следопыт",
        "description": "Разведчик маршрутов. Выживает за счёт наблюдательности, тихого движения и точного первого решения.",
        "weapon_type": "any",
        "weapon_keywords": [],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Слабое место",
                "description": "Следующая атака наносит +50% урона: следопыт выжидает момент и бьёт в уязвимость.",
                "energy_cost": 20,
                "cooldown": 3,
                "effect": {"damage_boost": 1.5},
            }
        ],
        "passive_skills": [
            {"name": "Тихий шаг", "required_level": 10, "description": "+6% к уклонению", "dodge": 6},
            {"name": "Глазомер", "required_level": 20, "description": "+6% к шансу крита", "crit_chance": 6},
            {"name": "Маршрутная память", "required_level": 35, "description": "+6% к редким находкам", "rare_find_chance": 6},
        ],
    },
    "штурмовик": {
        "class_id": "штурмовик",
        "name": "🛡️ Штурмовик",
        "description": "Линия давления. Держит удар, прикрывает отход и вытаскивает бой из плохой позиции.",
        "weapon_type": "any",
        "weapon_keywords": [],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Заслон",
                "description": "Даёт +14 защиты до ближайшей атаки врага.",
                "energy_cost": 18,
                "cooldown": 4,
                "effect": {"temp_defense": 14},
            }
        ],
        "passive_skills": [
            {"name": "Упор", "required_level": 10, "description": "+4 к защите", "defense": 4},
            {"name": "Темп атаки", "required_level": 20, "description": "+7% урона оружием", "weapon_damage": 7},
            {"name": "Плотная стойка", "required_level": 35, "description": "+5 к защите", "defense": 5},
        ],
    },
    "санитар": {
        "class_id": "санитар",
        "name": "🩺 Санитар",
        "description": "Полевой спасатель. Не самый громкий боец, зато чаще других доживает до эвакуации.",
        "weapon_type": "any",
        "weapon_keywords": [],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Полевой шов",
                "description": "Срочно восстанавливает часть HP прямо в бою.",
                "energy_cost": 24,
                "cooldown": 5,
                "effect": {"self_heal": 45},
            }
        ],
        "passive_skills": [
            {"name": "Перевязка на ходу", "required_level": 10, "description": "+3 к защите", "defense": 3},
            {"name": "Медицинская сумка", "required_level": 20, "description": "+8 кг переносимого веса", "max_weight": 8},
            {"name": "Живучесть", "required_level": 35, "description": "+2 к выносливости", "stamina": 2},
        ],
    },
    "техник": {
        "class_id": "техник",
        "name": "🔧 Техник",
        "description": "Специалист по снаряжению. Чинит, усиливает, тащит лишнее и превращает хлам в преимущество.",
        "weapon_type": "any",
        "weapon_keywords": [],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Полевая доработка",
                "description": "Следующая атака наносит больше урона за счёт быстрой настройки оружия и хвата.",
                "energy_cost": 19,
                "cooldown": 5,
                "effect": {"damage_boost": 1.35},
            }
        ],
        "passive_skills": [
            {"name": "Разгрузка", "required_level": 10, "description": "+10 кг переносимого веса", "max_weight": 10},
            {"name": "Настройка механизмов", "required_level": 20, "description": "+5% урона оружием", "weapon_damage": 5},
            {"name": "Усиленные пластины", "required_level": 35, "description": "+4 к защите", "defense": 4},
        ],
    },
    "аномалист": {
        "class_id": "аномалист",
        "name": "☢️ Аномалист",
        "description": "Ходок по искажённым местам. Читает поведение Зоны, датчики и странные тени у края зрения.",
        "weapon_type": "any",
        "weapon_keywords": [],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Срыв контура",
                "description": "Ослабляет ближайшую атаку врага, сбивая его темп аномальным импульсом.",
                "energy_cost": 21,
                "cooldown": 4,
                "effect": {"enemy_damage_reduction": 0.40},
            }
        ],
        "passive_skills": [
            {"name": "Чутьё искажений", "required_level": 10, "description": "+5% к редким находкам", "rare_find_chance": 5},
            {"name": "Холодный расчёт", "required_level": 20, "description": "+4% к уклонению", "dodge": 4},
            {"name": "Резонанс", "required_level": 35, "description": "+6% к критическому урону", "crit_damage": 6},
        ],
    },
    "охотник": {
        "class_id": "охотник",
        "name": "🐾 Охотник",
        "description": "Специалист по живым угрозам Зоны. Не гонится за честным боем, он читает повадки и добивает быстро.",
        "weapon_type": "any",
        "weapon_keywords": [],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Ложный след",
                "description": "Гарантированно срывает следующую атаку врага.",
                "energy_cost": 18,
                "cooldown": 4,
                "effect": {"perfect_dodge": 1},
            }
        ],
        "passive_skills": [
            {"name": "Звериная реакция", "required_level": 10, "description": "+5% к уклонению", "dodge": 5},
            {"name": "Добивание", "required_level": 20, "description": "+7% к шансу крита", "crit_chance": 7},
            {"name": "Разделка добычи", "required_level": 35, "description": "+6% урона оружием", "weapon_damage": 6},
        ],
    },
}


def _load_default_classes() -> dict:
    return json.loads(json.dumps(_DEFAULT_CLASSES))


def normalize_class_id(class_id: Optional[str]) -> Optional[str]:
    """Нормализовать class_id (legacy/алиасы/варианты написания)."""
    if not class_id:
        return None
    norm = str(class_id).strip().lower()
    if not norm:
        return None
    if norm in _CLASS_ID_ALIASES:
        return _CLASS_ID_ALIASES[norm]
    if "ё" not in norm and "е" in norm:
        yo_variant = norm.replace("е", "ё")
        if yo_variant in _DEFAULT_CLASSES:
            return yo_variant
    return norm


def _load_classes_from_db():
    """Загрузить классы из БД"""
    global _classes_cache
    if _classes_cache is not None:
        return _classes_cache
    
    from infra import database
    _classes_cache = {}
    
    try:
        has_api = all(
            hasattr(database, fn_name) for fn_name in (
                "get_all_classes_from_db",
                "get_class_active_skills",
                "get_class_passive_skills",
            )
        )
        if not has_api:
            _classes_cache = _load_default_classes()
            return _classes_cache

        classes = database.get_all_classes_from_db() or []
        legacy_class_ids = {
            "пистолетчик", "автоматчик", "снайпер", "пулемётчик", "пулеметчик", "дробовик", "боец",
        }
        raw_db_class_ids = {str(class_data.get('class_id', '')).strip().lower() for class_data in classes}
        # Старые таблицы классов были привязаны к типам оружия. Если в БД лежит именно
        # такой набор, используем новый кодовый набор, чтобы классы стали ролью игрока.
        if raw_db_class_ids and raw_db_class_ids.issubset(legacy_class_ids):
            _classes_cache = _load_default_classes()
            return _classes_cache

        for class_data in classes:
            class_id = normalize_class_id(class_data['class_id'])
            if not class_id:
                continue

            # Загружаем активные навыки
            active_skills = database.get_class_active_skills(class_id) or []
            formatted_active = []
            for skill in active_skills:
                formatted_active.append({
                    "name": skill['name'],
                    "description": skill['description'],
                    "energy_cost": skill['energy_cost'],
                    "cooldown": skill['cooldown'],
                    "effect": json.loads(skill['effect_json']) if skill['effect_json'] else {}
                })

            # Загружаем пассивные навыки
            passive_skills = database.get_class_passive_skills(class_id) or []
            formatted_passive = []
            for skill in passive_skills:
                bonuses = json.loads(skill['bonus_json']) if skill['bonus_json'] else {}
                formatted_passive.append({
                    "name": skill['name'],
                    "required_level": skill['required_level'],
                    "description": skill['description'],
                    **bonuses
                })

            required_weapons_raw = class_data.get('required_weapons')
            if isinstance(required_weapons_raw, str):
                try:
                    required_weapons = json.loads(required_weapons_raw) if required_weapons_raw else []
                except Exception:
                    required_weapons = [w.strip() for w in required_weapons_raw.split(",") if w.strip()]
            elif isinstance(required_weapons_raw, list):
                required_weapons = required_weapons_raw
            else:
                required_weapons = []

            weapon_keywords_raw = class_data.get('weapon_keywords', [])
            if isinstance(weapon_keywords_raw, str):
                try:
                    weapon_keywords = json.loads(weapon_keywords_raw) if weapon_keywords_raw else []
                except Exception:
                    weapon_keywords = [w.strip() for w in weapon_keywords_raw.split(",") if w.strip()]
            elif isinstance(weapon_keywords_raw, list):
                weapon_keywords = weapon_keywords_raw
            else:
                weapon_keywords = []

            # Сохраняем класс
            _classes_cache[class_id] = {
                "class_id": class_id,
                "name": class_data.get('name', class_id),
                "description": class_data.get('description', ''),
                "weapon_type": class_data.get('weapon_type', ''),
                "weapon_keywords": weapon_keywords,
                "required_weapons": required_weapons,
                "active_skills": formatted_active,
                "passive_skills": formatted_passive
            }
    except Exception:
        _classes_cache = _load_default_classes()
        return _classes_cache

    if not _classes_cache:
        _classes_cache = _load_default_classes()
    
    return _classes_cache


def _get_classes_dict() -> dict:
    """Получить словарь классов (загружает из БД при необходимости)"""
    return _load_classes_from_db()


# === Классы и функции ===

class PlayerClass:
    """Класс персонажа"""
    
    def __init__(self, class_id: str):
        self.id = class_id
        classes = _get_classes_dict()
        self.data = classes.get(class_id, {})
    
    @property
    def name(self) -> str:
        return self.data.get("name", "")
    
    @property
    def description(self) -> str:
        return self.data.get("description", "")
    
    @property
    def weapon_type(self) -> str:
        return self.data.get("weapon_type", "")
    
    @property
    def required_weapons(self) -> list:
        return self.data.get("required_weapons", [])
    
    @property
    def active_skills(self) -> list[dict]:
        return self.data.get("active_skills", [])
    
    @property
    def passive_skills(self) -> list[dict]:
        return self.data.get("passive_skills", [])


def get_class(class_id: str) -> Optional[PlayerClass]:
    """Получить класс по ID"""
    class_id = normalize_class_id(class_id)
    if not class_id:
        return None
    classes = _get_classes_dict()
    if class_id not in classes:
        return None
    return PlayerClass(class_id)


def get_all_classes() -> dict:
    """Получить все классы"""
    return _get_classes_dict()


def get_class_by_weapon(weapon_name: str) -> Optional[str]:
    """Классы больше не определяются оружием: оружие можно менять свободно."""
    return None


def get_available_classes(equipped_weapon: str = None) -> list[str]:
    """Получить доступные классы. Все специализации работают с любым оружием."""
    return list(_get_classes_dict().keys())


def format_class_info(class_id: str, player_level: int = None) -> str:
    """Форматировать информацию о классе для отображения"""
    player_class = get_class(class_id)
    if not player_class:
        return "Класс не найден"
    
    msg = f"{player_class.name}\n"
    msg += f"{player_class.description}\n\n"
    
    if player_class.required_weapons:
        msg += "📦Требуемое оружие: "
        msg += ", ".join(player_class.required_weapons) + "\n\n"
    else:
        msg += "📦Оружие: любое экипированное\n\n"
    
    msg += "⚡Активные навыки:\n"
    for skill in player_class.active_skills:
        msg += f"• {skill['name']} — {skill['description']} "
        msg += f"({skill['energy_cost']} энергии, перезарядка: {skill['cooldown']} ходов)\n"
    
    return msg


def get_passive_bonuses(class_id: str, player_level: int) -> dict:
    """Получить бонусы пассивных навыков для указанного уровня игрока"""
    class_id = normalize_class_id(class_id)
    player_class = get_class(class_id)
    if not player_class:
        return {}
    
    bonuses = {}
    
    for passive in player_class.passive_skills:
        required = passive.get("required_level", 10)
        if player_level >= required:
            # Добавляем все бонусы этого навыка (исключая мета-поля)
            for key, value in passive.items():
                if key not in ["name", "description", "required_level"]:
                    bonuses[key] = bonuses.get(key, 0) + value
    
    return bonuses


def get_unlocked_passives(class_id: str, player_level: int) -> list:
    """Получить список разблокированных пассивных навыков"""
    player_class = get_class(class_id)
    if not player_class:
        return []
    
    unlocked = []
    for passive in player_class.passive_skills:
        required = passive.get("required_level", 10)
        if player_level >= required:
            unlocked.append(passive)
    
    return unlocked


def format_passive_status(class_id: str, player_level: int) -> str:
    """Форматировать статус пассивных навыков"""
    player_class = get_class(class_id)
    if not player_class:
        return ""
    
    msg = "🔮Пассивные навыки:\n"
    
    for passive in player_class.passive_skills:
        required = passive.get("required_level", 10)
        if player_level >= required:
            status = "✅"
        else:
            status = "🔒"
        msg += f"{status} {passive['name']} (ур. {required})\n"
    
    return msg


def format_all_classes() -> str:
    """Форматировать список всех классов"""
    classes = _get_classes_dict()
    msg = "🎭Доступные классы:\n\n"
    
    for class_id, data in classes.items():
        weapons = ", ".join(data.get("required_weapons", [])) or "любое"
        active_count = len(data.get("active_skills", []))
        passive_count = len(data.get("passive_skills", []))
        
        msg += f"{data['name']}\n"
        msg += f"   Оружие: {weapons}\n"
        msg += f"   Пассивные: {passive_count} | Активные: {active_count}\n\n"
    
    return msg


def reload_classes():
    """Перезагрузить классы из БД (очистить кэш)"""
    global _classes_cache
    _classes_cache = None
    return _get_classes_dict()
