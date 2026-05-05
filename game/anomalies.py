# Аномалии Зоны
# =================
from __future__ import annotations
# Редкость артефактов:
# - common (обычный): легко найти, низкая цена
# - rare (редкий): средняя сложность, средняя цена
# - unique (уникальный): сложно найти, высокая цена
# - legendary (легендарный): очень редко, очень высокая цена

# Типы аномалий
ANOMALIES = {
    "жарка": {
        "name": "Жарка",
        "icon": "🔥",
        "description": "Плазменный огонь, который сжигает всё живое. Температура настолько высока, что металл плавится.",
        "danger_level": "высокая",
        "damage_without_detector": [30, 60],
        "damage_with_detector": [5, 15],
        "artifacts": ["Медуза", "Слюда", "Огненный шар", "Кровь камня", "Каменный цветок", "Кристалл"],
        "success_chance_with_detector": 55,
        "fail_damage_chance": 12,
        "artifact_types": ["thermal"],
        "difficulty": "high"
    },
    "электра": {
        "name": "Электра",
        "icon": "⚡",
        "description": "Мощные разряды тока, пронизывающие пространство. Слышно потрескивание на расстоянии.",
        "danger_level": "средняя",
        "damage_without_detector": [20, 40],
        "damage_with_detector": [5, 10],
        "artifacts": ["Бенгальский огонь", "Вспышка", "Батарейка", "Морской ёж"],
        "success_chance_with_detector": 60,
        "fail_damage_chance": 10,
        "artifact_types": ["electromagnetic"],
        "difficulty": "medium"
    },
    "воронка": {
        "name": "Воронка",
        "icon": "🌀",
        "description": "Гравитационный вихрь, затягивающий всё в себя. Предметы летают вокруг центра.",
        "danger_level": "высокая",
        "damage_without_detector": [40, 80],
        "damage_with_detector": [10, 20],
        "artifacts": ["Грави", "Пружина", "Золотая рыбка", "Ночная звезда", "Мамины бусы", "Лунный свет", "Колобок"],
        "success_chance_with_detector": 45,
        "fail_damage_chance": 15,
        "artifact_types": ["gravitational"],
        "difficulty": "high"
    },
    "туман": {
        "name": "Туман",
        "icon": "💨",
        "description": "Радиоактивный туман, скрывающий опасность. Плотный, как молоко, и такой же смертоносный.",
        "danger_level": "низкая",
        "damage_without_detector": [10, 25],
        "damage_with_detector": [0, 5],
        "artifacts": ["Слизь", "Капля", "Плёнка", "Слизняк", "Ломоть мяса", "Колобок"],
        "success_chance_with_detector": 70,
        "fail_damage_chance": 5,
        "artifact_types": ["biochemical"],
        "difficulty": "low"
    },
    "магнит": {
        "name": "Магнит",
        "icon": "🧲",
        "description": "Аномальное магнитное поле, притягивающее металл. Бьёт током при контакте.",
        "danger_level": "средняя",
        "damage_without_detector": [15, 35],
        "damage_with_detector": [5, 10],
        "artifacts": ["Пустышка", "Колючка", "Кристальная колючка", "Кристалл", "Батарейка"],
        "success_chance_with_detector": 60,
        "fail_damage_chance": 10,
        "artifact_types": ["electromagnetic", "crystalline"],
        "difficulty": "medium"
    },
    "пси-поле": {
        "name": "Пси-поле",
        "icon": "🧠",
        "description": "Пульсирующая зона ментального давления. Шумит в висках и сбивает направление.",
        "danger_level": "высокая",
        "damage_without_detector": [25, 55],
        "damage_with_detector": [6, 16],
        "artifacts": ["Выверт", "Лунный свет", "Мамины бусы", "Душа"],
        "success_chance_with_detector": 48,
        "fail_damage_chance": 14,
        "artifact_types": ["psi"],
        "difficulty": "high"
    },
    "кислотная топь": {
        "name": "Кислотная топь",
        "icon": "🧪",
        "description": "Зелёные лужи шипят под травой. Почва проседает и разъедает подошвы.",
        "danger_level": "средняя",
        "damage_without_detector": [18, 38],
        "damage_with_detector": [4, 10],
        "artifacts": ["Капля", "Слизь", "Плёнка", "Ломоть мяса", "Слизняк"],
        "success_chance_with_detector": 64,
        "fail_damage_chance": 9,
        "artifact_types": ["biochemical"],
        "difficulty": "medium"
    },
    "пространственный сдвиг": {
        "name": "Пространственный сдвиг",
        "icon": "〰️",
        "description": "Кусок пространства дрожит и смещает предметы на несколько шагов в сторону.",
        "danger_level": "высокая",
        "damage_without_detector": [35, 75],
        "damage_with_detector": [8, 18],
        "artifacts": ["Пружина", "Грави", "Ночная звезда", "Колобок", "Золотая рыбка", "Душа"],
        "success_chance_with_detector": 44,
        "fail_damage_chance": 16,
        "artifact_types": ["gravitational"],
        "difficulty": "high"
    },
    "электрошквал": {
        "name": "Электрошквал",
        "icon": "🌩️",
        "description": "Разряды бегут по воздуху цепью, как короткая гроза на уровне земли.",
        "danger_level": "высокая",
        "damage_without_detector": [28, 58],
        "damage_with_detector": [6, 14],
        "artifacts": ["Бенгальский огонь", "Вспышка", "Батарейка", "Морской ёж"],
        "success_chance_with_detector": 54,
        "fail_damage_chance": 13,
        "artifact_types": ["electromagnetic"],
        "difficulty": "high"
    },
    "радиационный карман": {
        "name": "Радиационный карман",
        "icon": "☢️",
        "description": "Невидимое пятно фонит волнами. Детектор щёлкает чаще с каждым шагом.",
        "danger_level": "средняя",
        "damage_without_detector": [16, 36],
        "damage_with_detector": [3, 9],
        "artifacts": ["Капля", "Плёнка", "Слизь", "Слизняк", "Выверт"],
        "success_chance_with_detector": 58,
        "fail_damage_chance": 8,
        "artifact_types": ["biochemical", "psi"],
        "difficulty": "medium"
    },
    "огненный разлом": {
        "name": "Огненный разлом",
        "icon": "♨️",
        "description": "Тонкая трещина в земле выдыхает жаром и красным светом.",
        "danger_level": "высокая",
        "damage_without_detector": [38, 82],
        "damage_with_detector": [10, 22],
        "artifacts": ["Слюда", "Огненный шар", "Кровь камня", "Каменный цветок", "Кристалл"],
        "success_chance_with_detector": 42,
        "fail_damage_chance": 18,
        "artifact_types": ["thermal"],
        "difficulty": "high"
    }
}

# Артефакты и их бонусы
ARTIFACTS = {
    # Обычные артефакты
    "Медуза": {
        "description": "Светящийся артефакт, напоминающий медузу. Даёт защиту от физического урона.",
        "bonus": "+15% к сопротивлению урону",
        "bonus_type": "damage_resist",
        "bonus_value": 15,
        "weight": 0.5,
        "price": 800,
        "rarity": "rare"
    },
    "Камень": {
        "description": "Плотный артефакт с аномальными свойствами. Увеличивает защиту.",
        "bonus": "+5 к защите",
        "bonus_type": "armor",
        "bonus_value": 5,
        "weight": 1.0,
        "price": 600,
        "rarity": "common"
    },
    "Грозовая": {
        "description": "Искрящийся артефакт. Увеличивает шанс критического удара.",
        "bonus": "+10% к критическому удару",
        "bonus_type": "crit_chance",
        "bonus_value": 10,
        "weight": 0.3,
        "price": 1000,
        "rarity": "rare"
    },
    "Пустышка": {
        "description": "Пустой артефакт, но обладает полезными свойствами. Увеличивает удачу.",
        "bonus": "+5 к удаче",
        "bonus_type": "luck",
        "bonus_value": 5,
        "weight": 0.2,
        "price": 500,
        "rarity": "common"
    },
    "Воронка": {
        "description": "Артефакт в форме воронки. Значительно увеличивает шанс находок.",
        "bonus": "+20% к находкам",
        "bonus_type": "find_chance",
        "bonus_value": 20,
        "weight": 0.8,
        "price": 1200,
        "rarity": "rare"
    },
    "Слизь": {
        "description": "Скользкий артефакт. Восстанавливает здоровье.",
        "bonus": "+10 HP",
        "bonus_type": "health",
        "bonus_value": 10,
        "weight": 0.4,
        "price": 400,
        "rarity": "common"
    },
    "Пыль": {
        "description": "Лёгкий артефакт, похожий на пыль. Помогает уклоняться.",
        "bonus": "+5% к уклонению",
        "bonus_type": "dodge",
        "bonus_value": 5,
        "weight": 0.1,
        "price": 550,
        "rarity": "common"
    },
    "Фрагмент": {
        "description": "Осколок аномалии. Увеличивает силу.",
        "bonus": "+5 к силе",
        "bonus_type": "strength",
        "bonus_value": 5,
        "weight": 0.6,
        "price": 700,
        "rarity": "common"
    },
    # Электромагнитные артефакты
    "Бенгальский огонь": {
        "description": "Яркий искрящийся артефакт. Увеличивает урон от электричества.",
        "bonus": "+15% к урону оружия",
        "bonus_type": "damage_boost",
        "bonus_value": 15,
        "weight": 0.3,
        "price": 1100,
        "rarity": "common",
        "artifact_type": "electromagnetic"
    },
    "Вспышка": {
        "description": "Мерцающий артефакт. Увеличивает дальность обнаружения.",
        "bonus": "+10% к находкам, +5 к восприятию",
        "bonus_type": "perception",
        "bonus_value": 5,
        "weight": 0.2,
        "price": 900,
        "rarity": "common",
        "artifact_type": "electromagnetic"
    },
    # Гравитационные артефакты
    "Грави": {
        "description": "Тяжёлый артефакт с искажающим полем. Значительно увеличивает защиту.",
        "bonus": "+20 к защите",
        "bonus_type": "armor",
        "bonus_value": 20,
        "weight": 2.0,
        "price": 2500,
        "rarity": "rare",
        "artifact_type": "gravitational"
    },
    "Золотая рыбка": {
        "description": "Редкий гравитационный артефакт. Приносит удачу.",
        "bonus": "+15 к удаче",
        "bonus_type": "luck",
        "bonus_value": 15,
        "weight": 0.5,
        "price": 3000,
        "rarity": "rare",
        "artifact_type": "gravitational"
    },
    "Ночная звезда": {
        "description": "Мерцающий гравитационный артефакт. Увеличивает грузоподъёмность.",
        "bonus": "+10 к максимальному весу",
        "bonus_type": "max_weight",
        "bonus_value": 10,
        "weight": 0.4,
        "price": 2200,
        "rarity": "rare",
        "artifact_type": "gravitational"
    },
    # Пси-активные артефакты
    "Выверт": {
        "description": "Нестабильный пси-артефакт. Увеличивает уклонение.",
        "bonus": "+15% к уклонению",
        "bonus_type": "dodge",
        "bonus_value": 15,
        "weight": 0.3,
        "price": 1800,
        "rarity": "rare",
        "artifact_type": "psi"
    },
    "Пузырь": {
        "description": "Полупрозрачный пси-артефакт. Увеличивает сопротивление урону.",
        "bonus": "+20% к сопротивлению урону",
        "bonus_type": "damage_resist",
        "bonus_value": 20,
        "weight": 0.4,
        "price": 2000,
        "rarity": "rare",
        "artifact_type": "psi"
    },
    "Лунный свет": {
        "description": "Светящийся пси-артефакт. Восстанавливает энергию.",
        "bonus": "+20 к максимальной энергии",
        "bonus_type": "max_energy",
        "bonus_value": 20,
        "weight": 0.2,
        "price": 2800,
        "rarity": "rare",
        "artifact_type": "psi"
    }
}

# Типы артефактов по природе
ARTIFACT_TYPES = {
    "Бенгальский огонь": "electromagnetic",
    "Вспышка": "electromagnetic",
    "Грави": "gravitational",
    "Золотая рыбка": "gravitational",
    "Ночная звезда": "gravitational",
    "Выверт": "psi",
    "Пузырь": "psi",
    "Лунный свет": "psi",
}

# Редкие артефакты
RARE_ARTIFACTS = [
    "Медуза", "Грозовая", "Воронка", "Грави", "Золотая рыбка",
    "Ночная звезда", "Выверт", "Пузырь", "Лунный свет"
]

# Приборы
DEVICES = {
    "Детектор аномалий": {
        "description": "Старый базовый прибор для обнаружения аномалий. Показывает тип и опасность.",
        "bonus": "Видишь аномалии, +8% к шансу артефакта",
        "effect": "anomaly_detector",
        "bonus_value": 8,
        "weight": 0.5,
        "price": 800
    },
    "Детектор Отклик-0": {
        "description": "Учебный детектор с грубым контуром аномалий. Его достаточно, чтобы не идти вслепую.",
        "bonus": "Показывает тип аномалии и возможные артефакты, +6% к шансу добычи",
        "effect": "otklik_0",
        "bonus_value": 6,
        "weight": 0.45,
        "price": 250
    },
    "Детектор Отклик-1": {
        "description": "Первый нормальный апгрейд: сигнал стабильнее, ложных писков меньше.",
        "bonus": "+10% к базовому шансу артефакта",
        "effect": "otklik_1",
        "bonus_value": 10,
        "weight": 0.45,
        "price": 900
    },
    "Эхо-1": {
        "description": "Старое название начального детектора. По характеристикам близок к Отклик-1.",
        "bonus": "+10% к базовому шансу артефакта",
        "effect": "echo_1",
        "bonus_value": 10,
        "weight": 0.4,
        "price": 900
    },
    "Детектор Отклик-М": {
        "description": "Улучшенная версия с усиленным приёмником сигналов.",
        "bonus": "+14% к базовому шансу артефакта",
        "effect": "otklik_m",
        "bonus_value": 14,
        "weight": 0.5,
        "price": 1800
    },
    "Детектор Сканер-П": {
        "description": "Специализированный детектор для электромагнитных аномалий.",
        "bonus": "+16% базово, до +24% для электромагнитных артефактов",
        "effect": "scanner_p",
        "bonus_value": 16,
        "bonus_type": "electromagnetic",
        "type_bonus": 24,
        "weight": 0.6,
        "price": 3500
    },
    "Детектор Пеленг-3": {
        "description": "Профессиональный прибор с высокой точностью обнаружения.",
        "bonus": "+20% к базовому шансу артефакта",
        "effect": "peleng_3",
        "bonus_value": 20,
        "weight": 0.7,
        "price": 5000
    },
    "Детектор Гном-Т": {
        "description": "Тяжёлый, но мощный детектор для гравитационных аномалий.",
        "bonus": "+21% базово, до +28% для гравитационных артефактов",
        "effect": "gnom_t",
        "bonus_value": 21,
        "bonus_type": "gravitational",
        "type_bonus": 28,
        "weight": 1.2,
        "price": 6000
    },
    "Детектор-Х": {
        "description": "Экспериментальный прибор с повышенной чувствительностью.",
        "bonus": "+24% базово, до +32% для редких артефактов",
        "effect": "detector_x",
        "bonus_value": 24,
        "rare_bonus": 32,
        "weight": 0.5,
        "price": 7500
    },
    "Детектор Аномалист-2": {
        "description": "Популярный среди сталкеров прибор среднего класса.",
        "bonus": "+27% к базовому шансу артефакта",
        "effect": "anomalist_2",
        "bonus_value": 27,
        "weight": 0.6,
        "price": 6500
    },
    "Детектор Мираж-Альфа": {
        "description": "Специализированный детектор для пси-активных артефактов.",
        "bonus": "+28% базово, до +36% для пси-активных артефактов",
        "effect": "mirage_alpha",
        "bonus_value": 28,
        "bonus_type": "psi",
        "type_bonus": 36,
        "weight": 0.4,
        "price": 8000
    },
    "Око Зоны": {
        "description": "Легендарный детектор, разработанный учёными Зоны.",
        "bonus": "+32% базово, до +40% в скоплении аномалий",
        "effect": "oko_zony",
        "bonus_value": 32,
        "cluster_bonus": 40,
        "weight": 0.3,
        "price": 15000
    },
    "Компас": {
        "description": "Старый компас сталкера. Показывает направление.",
        "bonus": "+5% к находкам",
        "effect": "compass",
        "bonus_value": 5,
        "weight": 0.1,
        "price": 150
    },
    "Фонарик": {
        "description": "Источник света в темноте.",
        "bonus": "+5% к находкам ночью",
        "effect": "flashlight",
        "weight": 0.3,
        "price": 200
    },
    "Рация": {
        "description": "Связь с городом.",
        "bonus": "Связь с торговцами",
        "effect": "radio",
        "weight": 1.0,
        "price": 500
    }
}


def get_random_anomaly() -> dict:
    """Получить случайную аномалию"""
    import random
    anomaly_type = random.choice(list(ANOMALIES.keys()))
    return {
        "type": anomaly_type,
        **ANOMALIES[anomaly_type]
    }


def get_artifact_from_anomaly(anomaly_type: str) -> str | None:
    """Получить артефакт из аномалии (если повезёт)"""
    import random
    
    if anomaly_type not in ANOMALIES:
        return None
    
    anomaly = ANOMALIES[anomaly_type]
    artifacts_list = anomaly.get("artifacts", [])
    
    if not artifacts_list:
        return None
    
    return random.choice(artifacts_list)


def get_equipped_detector(player) -> dict | None:
    """Получить экипированный детектор и его бонусы"""
    equipped_device = getattr(player, 'equipped_device', None)
    if not equipped_device:
        return None

    # Ищем детектор по названию
    for device_name, device_data in DEVICES.items():
        if _device_names_match(device_name, equipped_device):
            return {
                "name": device_name,
                **device_data
            }

    return None


def _device_names_match(canonical_name: str, item_name: str) -> bool:
    canonical = str(canonical_name or "").lower()
    actual = str(item_name or "").lower()
    return bool(canonical and actual and (canonical in actual or actual in canonical))


def is_detector_name(item_name: str) -> bool:
    """Проверить, является ли предмет известным детектором."""
    normalized = str(item_name or "").lower()
    if "детектор" in normalized:
        return True
    return any(
        _device_names_match(device_name, item_name)
        for device_name, device_data in DEVICES.items()
        if device_data.get("effect") != "compass"
    )


def get_detector_bonus(player, artifact_type: str = None, is_rare: bool = False, in_cluster: bool = False) -> int:
    """Получить бонус детектора к шансу артефакта"""
    detector = get_equipped_detector(player)
    if not detector:
        return 0

    bonus = int(detector.get("bonus_value", 0) or 0)

    # Бонус для специфических типов артефактов
    if artifact_type and detector.get("bonus_type") == artifact_type:
        bonus = max(bonus, int(detector.get("type_bonus", detector.get("bonus_value", 0)) or 0))

    # Бонус для редких артефактов (Детектор-Х)
    if is_rare and "rare_bonus" in detector:
        bonus = max(bonus, detector["rare_bonus"])

    # Бонус для скопления аномалий (Око Зоны)
    if in_cluster and "cluster_bonus" in detector:
        bonus = max(bonus, detector["cluster_bonus"])

    return bonus
