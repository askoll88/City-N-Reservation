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
        "description": (
            "Следопыт не идёт по дороге — он заранее знает, где дорога предаст. "
            "Таких зовут первыми, когда нужно пройти через серую зону без карты, найти обход патруля, "
            "заметить свежую растяжку или понять, почему лес вдруг замолчал. Он не самый громкий в бою, "
            "но часто именно его первый выстрел решает, будет ли бой вообще. "
            "Это класс для тех, кто хочет чувствовать себя глазами группы: видеть больше, рисковать умнее, "
            "забирать редкое там, где остальные проходят мимо."
        ),
        "weapon_type": "any",
        "weapon_keywords": [],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Слабое место",
                "description": (
                    "Следопыт выжидает короткий провал в движении врага и бьёт туда, "
                    "где броня, шкура или рефлекс дают сбой. Следующая атака наносит +50% урона."
                ),
                "energy_cost": 20,
                "cooldown": 3,
                "effect": {"damage_boost": 1.5},
            }
        ],
        "passive_skills": [
            {"name": "Тихий шаг", "required_level": 10, "description": "привычка ставить ногу туда, где Зона не ждёт; +6% к уклонению", "dodge": 6},
            {"name": "Глазомер", "required_level": 20, "description": "умение ловить правильную долю секунды; +6% к шансу крита", "crit_chance": 6},
            {"name": "Маршрутная память", "required_level": 35, "description": "память на тайники, тропы и чужие ошибки; +6% к редким находкам", "rare_find_chance": 6},
        ],
    },
    "штурмовик": {
        "class_id": "штурмовик",
        "name": "🛡️ Штурмовик",
        "description": (
            "Штурмовик — это человек, за спиной которого перестают паниковать. "
            "Когда коридор простреливается, мутант уже в прыжке, а отступление превратилось в давку, "
            "он делает шаг вперёд и превращает хаос в линию боя. Его работа не в том, чтобы выглядеть красиво, "
            "а в том, чтобы выдержать первый удар, навязать темп и дать остальным шанс дышать. "
            "Это класс для игроков, которые хотят быть опорой в бою: меньше бояться ответки, давить стабильнее "
            "и вывозить опасные столкновения, где тонкие билды сыпятся."
        ),
        "weapon_type": "any",
        "weapon_keywords": [],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Заслон",
                "description": (
                    "Штурмовик принимает позицию, закрывает корпус и ловит удар на снаряжение. "
                    "Даёт +14 защиты до ближайшей атаки врага."
                ),
                "energy_cost": 18,
                "cooldown": 4,
                "effect": {"temp_defense": 14},
            }
        ],
        "passive_skills": [
            {"name": "Упор", "required_level": 10, "description": "тело уже знает, как встретить удар; +4 к защите", "defense": 4},
            {"name": "Темп атаки", "required_level": 20, "description": "давление не даёт врагу восстановиться; +7% урона оружием", "weapon_damage": 7},
            {"name": "Плотная стойка", "required_level": 35, "description": "штурмовика сложнее сдвинуть, чем убить; +5 к защите", "defense": 5},
        ],
    },
    "санитар": {
        "class_id": "санитар",
        "name": "🩺 Санитар",
        "description": (
            "Санитар знает, как звучит человек за минуту до смерти, и не любит этот звук. "
            "Он носит не только бинты: он носит вторые шансы, чужие долги и привычку работать руками, "
            "когда вокруг стреляют. В рейде Санитар ценится не за громкие убийства, а за то, что после плохой встречи "
            "кто-то всё ещё стоит на ногах. Это класс для тех, кто устал платить больнице после каждого выхода "
            "и хочет иметь аварийный запас живучести прямо в бою. Меньше блеска, больше возвращений домой."
        ),
        "weapon_type": "any",
        "weapon_keywords": [],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Полевой шов",
                "description": (
                    "Санитар стягивает рану, глушит боль и заставляет тело держаться ещё немного. "
                    "Срочно восстанавливает часть HP прямо в бою."
                ),
                "energy_cost": 24,
                "cooldown": 5,
                "effect": {"self_heal": 45},
            }
        ],
        "passive_skills": [
            {"name": "Перевязка на ходу", "required_level": 10, "description": "мелкие раны не выбивают из темпа; +3 к защите", "defense": 3},
            {"name": "Медицинская сумка", "required_level": 20, "description": "место под ампулы, бинты и лишний шанс; +8 кг переносимого веса", "max_weight": 8},
            {"name": "Живучесть", "required_level": 35, "description": "организм привык работать на последнем ресурсе; +2 к выносливости", "stamina": 2},
        ],
    },
    "техник": {
        "class_id": "техник",
        "name": "🔧 Техник",
        "description": (
            "Техник смотрит на чужой хлам и видит будущий перевес. "
            "Для него Зона — не только мутанты и аномалии, а тысячи сломанных механизмов, перекошенных креплений, "
            "перетёртых ремней и недособранных решений. Он не верит в идеальное снаряжение: он делает своё снаряжение "
            "достаточно хорошим прямо сейчас. Это класс для тех, кто любит практичную силу: больше нести, лучше выжимать "
            "урон из любого оружия, крепче держаться за счёт доработок и подготовки."
        ),
        "weapon_type": "any",
        "weapon_keywords": [],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Полевая доработка",
                "description": (
                    "Техник на ходу подтягивает крепление, меняет хват, находит нужный режим и выжимает из оружия больше, "
                    "чем оно обещало на бумаге. Следующая атака наносит повышенный урон."
                ),
                "energy_cost": 19,
                "cooldown": 5,
                "effect": {"damage_boost": 1.35},
            }
        ],
        "passive_skills": [
            {"name": "Разгрузка", "required_level": 10, "description": "каждый ремень на месте, каждый карман работает; +10 кг переносимого веса", "max_weight": 10},
            {"name": "Настройка механизмов", "required_level": 20, "description": "оружие стреляет ровнее, чем должно; +5% урона оружием", "weapon_damage": 5},
            {"name": "Усиленные пластины", "required_level": 35, "description": "самодельные правки держат там, где завод сэкономил; +4 к защите", "defense": 4},
        ],
    },
    "аномалист": {
        "class_id": "аномалист",
        "name": "☢️ Аномалист",
        "description": (
            "Аномалист — из тех, кто не отводит взгляд, когда воздух начинает дрожать. "
            "Обычные сталкеры обходят пятна, где компас врёт и металл тихо поёт; Аномалист слушает, запоминает, "
            "а иногда делает шаг ближе. Он живёт на границе науки, суеверия и нервного срыва. "
            "Его сила не в прямом напоре, а в умении использовать странность Зоны против тех, кто слишком прямолинеен. "
            "Это класс для игроков, которым хочется мистики, редких находок и ощущения, что сама Зона иногда отвечает."
        ),
        "weapon_type": "any",
        "weapon_keywords": [],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Срыв контура",
                "description": (
                    "Аномалист ловит нестабильность рядом и срывает вражеский темп коротким аномальным импульсом. "
                    "Ближайшая атака врага заметно слабеет."
                ),
                "energy_cost": 21,
                "cooldown": 4,
                "effect": {"enemy_damage_reduction": 0.40},
            }
        ],
        "passive_skills": [
            {"name": "Чутьё искажений", "required_level": 10, "description": "редкое чаще откликается тем, кто умеет слушать; +5% к редким находкам", "rare_find_chance": 5},
            {"name": "Холодный расчёт", "required_level": 20, "description": "паника убивает быстрее радиации; +4% к уклонению", "dodge": 4},
            {"name": "Резонанс", "required_level": 35, "description": "удар попадает в момент, когда мир уже треснул; +6% к критическому урону", "crit_damage": 6},
        ],
    },
    "охотник": {
        "class_id": "охотник",
        "name": "🐾 Охотник",
        "description": (
            "Охотник не считает мутантов чудовищами. Для него это следы, запах, голод, территория и ошибка в повадке. "
            "Он не играет в честную дуэль: заманивает, сбивает с курса, ждёт лишний шаг и бьёт, когда добыча уже решила, "
            "что победила. Люди рядом с ним чувствуют себя не безопаснее, а тише — потому что понимают, насколько мало "
            "они сами замечали. Это класс для тех, кто хочет быть хищником Зоны: уходить от смертельной атаки, "
            "чаще критовать и добивать угрозы без лишней героики."
        ),
        "weapon_type": "any",
        "weapon_keywords": [],
        "required_weapons": [],
        "active_skills": [
            {
                "name": "Ложный след",
                "description": (
                    "Охотник оставляет врагу неверный ритм, неверный угол, неверную цель. "
                    "Следующая атака врага гарантированно срывается."
                ),
                "energy_cost": 18,
                "cooldown": 4,
                "effect": {"perfect_dodge": 1},
            }
        ],
        "passive_skills": [
            {"name": "Звериная реакция", "required_level": 10, "description": "тело дёргается раньше, чем мысль успевает назвать угрозу; +5% к уклонению", "dodge": 5},
            {"name": "Добивание", "required_level": 20, "description": "охотник видит момент, когда добыча уже проиграла; +7% к шансу крита", "crit_chance": 7},
            {"name": "Разделка добычи", "required_level": 35, "description": "каждый удар идёт туда, где живое ломается быстрее; +6% урона оружием", "weapon_damage": 6},
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
