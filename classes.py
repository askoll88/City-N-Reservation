"""
Система классов персонажей
Данные загружаются из БД
"""

import json
from typing import Optional


# Кэш классов в памяти
_classes_cache = None


# Fallback-набор классов, если БД не содержит таблиц/функций классов.
_DEFAULT_CLASSES = {
    "пистолетчик": {
        "class_id": "пистолетчик",
        "name": "🔫 Пистолетчик",
        "description": "Быстрый и точный боец на коротких дистанциях.",
        "weapon_type": "pistol",
        "weapon_keywords": ["пм", "глок", "гш", "пистолет", "glock", "beretta", "pistol"],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Точный выстрел",
                "description": "Следующая атака наносит +50% урона.",
                "energy_cost": 20,
                "cooldown": 3,
                "effect": {"damage_boost": 1.5},
            }
        ],
        "passive_skills": [
            {"name": "Быстрые руки", "required_level": 10, "description": "+5% к уклонению", "dodge": 5},
            {"name": "Холодная голова", "required_level": 20, "description": "+5% к шансу крита", "crit_chance": 5},
        ],
    },
    "автоматчик": {
        "class_id": "автоматчик",
        "name": "⚔️ Автоматчик",
        "description": "Универсальный штурмовик с упором в стабильный урон.",
        "weapon_type": "assault_rifle",
        "weapon_keywords": ["ак", "м4", "м16", "автомат", "scar", "ar-", "rifle"],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Бронирование",
                "description": "Временное усиление защиты в бою.",
                "energy_cost": 18,
                "cooldown": 4,
                "effect": {"temp_defense": 10},
            }
        ],
        "passive_skills": [
            {"name": "Штурмовой напор", "required_level": 10, "description": "+8% урона оружием", "weapon_damage": 8},
            {"name": "Полевая выучка", "required_level": 20, "description": "+4 к защите", "defense": 4},
        ],
    },
    "снайпер": {
        "class_id": "снайпер",
        "name": "🎯 Снайпер",
        "description": "Максимум урона за выстрел и повышенный крит.",
        "weapon_type": "sniper",
        "weapon_keywords": ["свд", "винтовк", "снайпер", "barrett", "awp", "sniper"],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Точный выстрел",
                "description": "Следующая атака наносит +50% урона.",
                "energy_cost": 22,
                "cooldown": 3,
                "effect": {"damage_boost": 1.5},
            }
        ],
        "passive_skills": [
            {"name": "Смертельная меткость", "required_level": 10, "description": "+10% шанса крита", "crit_chance": 10},
            {"name": "Выверенный выстрел", "required_level": 20, "description": "+15% к крит-урону", "crit_damage": 15},
        ],
    },
    "пулемётчик": {
        "class_id": "пулемётчик",
        "name": "💥 Пулемётчик",
        "description": "Тяжелый боец с высоким давлением огнем.",
        "weapon_type": "machine_gun",
        "weapon_keywords": ["пулем", "рпк", "м249", "pkm", "minigun"],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Заградительный огонь",
                "description": "Снижает входящий урон на несколько ходов.",
                "energy_cost": 25,
                "cooldown": 5,
                "effect": {"aoe_damage_reduction": 0.15},
            }
        ],
        "passive_skills": [
            {"name": "Тяжелый калибр", "required_level": 10, "description": "+10% урона оружием", "weapon_damage": 10},
            {"name": "Боевая устойчивость", "required_level": 20, "description": "+6 к защите", "defense": 6},
        ],
    },
    "дробовик": {
        "class_id": "дробовик",
        "name": "🏹 Дробовик",
        "description": "Крайне опасен на ближней дистанции.",
        "weapon_type": "shotgun",
        "weapon_keywords": ["дробов", "shotgun", "remington", "saiga", "тоз", "toz"],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Точный выстрел",
                "description": "Следующая атака наносит +50% урона.",
                "energy_cost": 18,
                "cooldown": 3,
                "effect": {"damage_boost": 1.5},
            }
        ],
        "passive_skills": [
            {"name": "Картечный залп", "required_level": 10, "description": "+8% урона оружием", "weapon_damage": 8},
            {"name": "Мясник", "required_level": 20, "description": "+8% шанса крита", "crit_chance": 8},
        ],
    },
    "боец": {
        "class_id": "боец",
        "name": "🔪 Боец",
        "description": "Мастер ближнего боя и выживаемости.",
        "weapon_type": "melee",
        "weapon_keywords": ["нож", "мачете", "топор", "финка", "knife", "machete", "dagger", "bayonet"],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Уклонение",
                "description": "Следующая вражеская атака с высокой вероятностью промахнется.",
                "energy_cost": 16,
                "cooldown": 4,
                "effect": {"perfect_dodge": 1},
            }
        ],
        "passive_skills": [
            {"name": "Реакция", "required_level": 10, "description": "+10% уклонения", "dodge": 10},
            {"name": "Стальная воля", "required_level": 20, "description": "+6 к защите", "defense": 6},
        ],
    },
}


def _load_default_classes() -> dict:
    return json.loads(json.dumps(_DEFAULT_CLASSES))


def _load_classes_from_db():
    """Загрузить классы из БД"""
    global _classes_cache
    if _classes_cache is not None:
        return _classes_cache
    
    import database
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
        for class_data in classes:
            class_id = class_data['class_id']

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
            required_weapons = json.loads(required_weapons_raw) if required_weapons_raw else []

            # Сохраняем класс
            _classes_cache[class_id] = {
                "class_id": class_id,
                "name": class_data.get('name', class_id),
                "description": class_data.get('description', ''),
                "weapon_type": class_data.get('weapon_type', ''),
                "weapon_keywords": class_data.get('weapon_keywords', []),
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
    classes = _get_classes_dict()
    if class_id not in classes:
        return None
    return PlayerClass(class_id)


def get_all_classes() -> dict:
    """Получить все классы"""
    return _get_classes_dict()


def get_class_by_weapon(weapon_name: str) -> Optional[str]:
    """Определить класс по оружию"""
    if not weapon_name:
        return None

    classes = _get_classes_dict()
    weapon_lower = weapon_name.lower().strip()

    # 1) точное совпадение с белым списком оружия
    for class_id, data in classes.items():
        required_weapons = data.get("required_weapons", [])
        if weapon_name in required_weapons:
            return class_id

    # 2) эвристика по ключевым словам (fallback)
    for class_id, data in classes.items():
        keywords = data.get("weapon_keywords", [])
        if any(k.lower() in weapon_lower for k in keywords):
            return class_id

    # 3) эвристика по типу класса (если keywords не заданы)
    if any(k in weapon_lower for k in ("нож", "мачете", "knife", "machete", "dagger", "bayonet")):
        return "боец"
    if any(k in weapon_lower for k in ("дробов", "shotgun", "saiga", "toz")):
        return "дробовик"
    if any(k in weapon_lower for k in ("снайпер", "свд", "sniper", "awp", "винтовк")):
        return "снайпер"
    if any(k in weapon_lower for k in ("пулем", "pkm", "m249", "minigun", "рпк")):
        return "пулемётчик"
    if any(k in weapon_lower for k in ("пистолет", "пм", "глок", "pistol", "glock", "beretta")):
        return "пистолетчик"
    if any(k in weapon_lower for k in ("автомат", "ак", "м4", "m4", "ar-", "scar", "rifle")):
        return "автоматчик"

    return None


def get_available_classes(equipped_weapon: str = None) -> list[str]:
    """Получить доступные классы (те, которые можно использовать с текущим оружием)"""
    if not equipped_weapon:
        return []
    
    classes = _get_classes_dict()
    available = []
    for class_id, data in classes.items():
        if equipped_weapon in data.get("required_weapons", []) or get_class_by_weapon(equipped_weapon) == class_id:
            available.append(class_id)
    return available


def format_class_info(class_id: str, player_level: int = None) -> str:
    """Форматировать информацию о классе для отображения"""
    player_class = get_class(class_id)
    if not player_class:
        return "Класс не найден"
    
    msg = f"{player_class.name}\n"
    msg += f"{player_class.description}\n\n"
    
    msg += "📦Требуемое оружие: "
    msg += ", ".join(player_class.required_weapons) + "\n\n"
    
    msg += "⚡Активные навыки:\n"
    for skill in player_class.active_skills:
        msg += f"• {skill['name']} — {skill['description']} "
        msg += f"({skill['energy_cost']} энергии, перезарядка: {skill['cooldown']} ходов)\n"
    
    return msg


def get_passive_bonuses(class_id: str, player_level: int) -> dict:
    """Получить бонусы пассивных навыков для указанного уровня игрока"""
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
        weapons = ", ".join(data.get("required_weapons", []))
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
