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
        "description": "Базовый прибор для обнаружения аномалий. Показывает тип и опасность.",
        "bonus": "Видишь аномалии, +10% шанс артефакта",
        "effect": "anomaly_detector",
        "bonus_value": 10,
        "weight": 0.5,
        "price": 800
    },
    "Эхо-1": {
        "description": "Недорогой детектор начального уровня. Хорош для новичков.",
        "bonus": "+15% к базовому шансу артефакта",
        "effect": "echo_1",
        "bonus_value": 15,
        "weight": 0.4,
        "price": 1200
    },
    "Отклик-М": {
        "description": "Улучшенная версия с усиленным приёмником сигналов.",
        "bonus": "+25% к базовому шансу артефакта",
        "effect": "otklik_m",
        "bonus_value": 25,
        "weight": 0.5,
        "price": 2500
    },
    "Сканер-П": {
        "description": "Специализированный детектор для электромагнитных аномалий.",
        "bonus": "+30% для электромагнитных артефактов (Бенгальский огонь, Вспышка)",
        "effect": "scanner_p",
        "bonus_value": 30,
        "bonus_type": "electromagnetic",
        "weight": 0.6,
        "price": 3500
    },
    "Пеленг-3": {
        "description": "Профессиональный прибор с высокой точностью обнаружения.",
        "bonus": "+40% к базовому шансу артефакта",
        "effect": "peleng_3",
        "bonus_value": 40,
        "weight": 0.7,
        "price": 5000
    },
    "Гном-Т": {
        "description": "Тяжёлый, но мощный детектор для гравитационных аномалий.",
        "bonus": "+50% для гравитационных артефактов (Грави, Золотая рыбка, Ночная звезда)",
        "effect": "gnom_t",
        "bonus_value": 50,
        "bonus_type": "gravitational",
        "weight": 1.2,
        "price": 6000
    },
    "Детектор-Х": {
        "description": "Экспериментальный прибор с повышенной чувствительностью.",
        "bonus": "+35% к базовому, +60% для редких артефактов",
        "effect": "detector_x",
        "bonus_value": 35,
        "rare_bonus": 60,
        "weight": 0.5,
        "price": 7500
    },
    "Аномалист-2": {
        "description": "Популярный среди сталкеров прибор среднего класса.",
        "bonus": "+45% к базовому шансу артефакта",
        "effect": "anomalist_2",
        "bonus_value": 45,
        "weight": 0.6,
        "price": 6500
    },
    "Мираж-Альфа": {
        "description": "Специализированный детектор для пси-активных артефактов.",
        "bonus": "+65% для пси-активных артефактов (Выверт, Пузырь, Лунный свет)",
        "effect": "mirage_alpha",
        "bonus_value": 65,
        "bonus_type": "psi",
        "weight": 0.4,
        "price": 8000
    },
    "Око Зоны": {
        "description": "Легендарный детектор, разработанный учёными Зоны.",
        "bonus": "+55% к базовому для всех типов, +80% в скоплении аномалий",
        "effect": "oko_zony",
        "bonus_value": 55,
        "cluster_bonus": 80,
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


def has_anomaly_detector(player) -> bool:
    """Проверить, есть ли у игрока детектор аномалий"""
    # Проверяем в экипированных устройствах
    equipped_device = getattr(player, 'equipped_device', None)
    if equipped_device:
        device_lower = equipped_device.lower()
        for device_name in DEVICES:
            if device_name.lower() in device_lower or device_lower in device_name.lower():
                return True

    # Проверяем в инвентаре
    player.inventory.reload()
    for item in player.inventory.other:
        item_name_lower = item['name'].lower()
        for device_name in DEVICES:
            if device_name.lower() in item_name_lower:
                return True

    return False


def get_equipped_detector(player) -> dict | None:
    """Получить экипированный детектор и его бонусы"""
    equipped_device = getattr(player, 'equipped_device', None)
    if not equipped_device:
        return None

    # Ищем детектор по названию
    for device_name, device_data in DEVICES.items():
        if device_name.lower() in equipped_device.lower() or equipped_device.lower() in device_name.lower():
            return {
                "name": device_name,
                **device_data
            }

    return None


def get_detector_bonus(player, artifact_type: str = None, is_rare: bool = False, in_cluster: bool = False) -> int:
    """Получить бонус детектора к шансу артефакта"""
    detector = get_equipped_detector(player)
    if not detector:
        return 0

    bonus = detector.get("bonus_value", 0)

    # Бонус для специфических типов артефактов
    if artifact_type and detector.get("bonus_type") == artifact_type:
        bonus = max(bonus, detector.get("bonus_value", 0))

    # Бонус для редких артефактов (Детектор-Х)
    if is_rare and "rare_bonus" in detector:
        bonus = max(bonus, detector["rare_bonus"])

    # Бонус для скопления аномалий (Око Зоны)
    if in_cluster and "cluster_bonus" in detector:
        bonus = max(bonus, detector["cluster_bonus"])

    return bonus


def get_detector_guaranteed_artifact(player) -> bool:
    """Проверить, гарантирует ли детектор хотя бы один артефакт"""
    detector = get_equipped_detector(player)
    if not detector:
        return False
    return detector.get("effect") == "compass"

