"""
Система классов персонажей
Данные загружаются из БД
"""

import json
from typing import Optional


# Кэш классов в памяти
_classes_cache = None


def _load_classes_from_db():
    """Загрузить классы из БД"""
    global _classes_cache
    if _classes_cache is not None:
        return _classes_cache
    
    import database
    _classes_cache = {}
    
    classes = database.get_all_classes_from_db()
    for class_data in classes:
        class_id = class_data['class_id']
        
        # Загружаем активные навыки
        active_skills = database.get_class_active_skills(class_id)
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
        passive_skills = database.get_class_passive_skills(class_id)
        formatted_passive = []
        for skill in passive_skills:
            bonuses = json.loads(skill['bonus_json']) if skill['bonus_json'] else {}
            formatted_passive.append({
                "name": skill['name'],
                "required_level": skill['required_level'],
                "description": skill['description'],
                **bonuses
            })
        
        # Сохраняем класс
        _classes_cache[class_id] = {
            "class_id": class_id,
            "name": class_data['name'],
            "description": class_data['description'],
            "weapon_type": class_data['weapon_type'],
            "required_weapons": json.loads(class_data['required_weapons']) if class_data['required_weapons'] else [],
            "active_skills": formatted_active,
            "passive_skills": formatted_passive
        }
    
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

    for class_id, data in classes.items():
        required_weapons = data.get("required_weapons", [])
        if weapon_name in required_weapons:
            return class_id

    return None


def get_available_classes(equipped_weapon: str = None) -> list[str]:
    """Получить доступные классы (те, которые можно использовать с текущим оружием)"""
    if not equipped_weapon:
        return []
    
    classes = _get_classes_dict()
    available = []
    for class_id, data in classes.items():
        if equipped_weapon in data.get("required_weapons", []):
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
