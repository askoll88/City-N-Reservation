# Аномалии Зоны

# Типы аномалий
ANOMALIES = {
    "жарка": {
        "name": "Жарка",
        "icon": "🔥",
        "description": "Плазменный огонь, который сжигает всё живое. Температура настолько высока, что металл плавится.",
        "danger_level": "высокая",
        "damage_without_detector": [30, 60],  # min, max урон
        "damage_with_detector": [5, 15],  # урон при ошибке детектора
        "artifacts": ["Медуза", "Камень"],
        "success_chance_with_detector": 60,  # % шанс получить артефакт
        "fail_damage_chance": 10  # % шанс получить урон при ошибке детектора
    },
    "электра": {
        "name": "Электра",
        "icon": "⚡",
        "description": "Мощные разряды тока, пронизывающие пространство. Слышно потрескивание на расстоянии.",
        "danger_level": "средняя",
        "damage_without_detector": [20, 40],
        "damage_with_detector": [5, 10],
        "artifacts": ["Грозовая", "Пустышка"],
        "success_chance_with_detector": 65,
        "fail_damage_chance": 10
    },
    "воронка": {
        "name": "Воронка",
        "icon": "🌀",
        "description": "Гравитационный вихрь, затягивающий всё в себя. Предметы летают вокруг центра.",
        "danger_level": "высокая",
        "damage_without_detector": [40, 80],
        "damage_with_detector": [10, 20],
        "artifacts": ["Воронка", "Медуза"],
        "success_chance_with_detector": 50,
        "fail_damage_chance": 15
    },
    "туман": {
        "name": "Туман",
        "icon": "💨",
        "description": "Радиоактивный туман, скрывающий опасность. Плотный, как молоко, и такой же смертоносный.",
        "danger_level": "низкая",
        "damage_without_detector": [10, 25],
        "damage_with_detector": [0, 5],
        "artifacts": ["Слизь", "Пыль"],
        "success_chance_with_detector": 70,
        "fail_damage_chance": 5
    },
    "магнит": {
        "name": "Магнит",
        "icon": "🧲",
        "description": "Аномальное магнитное поле, притягивающее металл. Бьёт током при контакте.",
        "danger_level": "средняя",
        "damage_without_detector": [15, 35],
        "damage_with_detector": [5, 10],
        "artifacts": ["Фрагмент", "Пустышка"],
        "success_chance_with_detector": 60,
        "fail_damage_chance": 10
    }
}

# Артефакты и их бонусы
ARTIFACTS = {
    "Медуза": {
        "description": "Светящийся артефакт, напоминающий медузу. Даёт защиту от физического урона.",
        "bonus": "+15% к сопротивлению урону",
        "bonus_type": "damage_resist",
        "bonus_value": 15,
        "weight": 0.5,
        "price": 800
    },
    "Камень": {
        "description": "Плотный артефакт с аномальными свойствами. Увеличивает защиту.",
        "bonus": "+5 к защите",
        "bonus_type": "armor",
        "bonus_value": 5,
        "weight": 1.0,
        "price": 600
    },
    "Грозовая": {
        "description": "Искрящийся артефакт. Увеличивает шанс критического удара.",
        "bonus": "+10% к критическому удару",
        "bonus_type": "crit_chance",
        "bonus_value": 10,
        "weight": 0.3,
        "price": 1000
    },
    "Пустышка": {
        "description": "Пустой артефакт, но обладает полезными свойствами. Увеличивает удачу.",
        "bonus": "+5 к удаче",
        "bonus_type": "luck",
        "bonus_value": 5,
        "weight": 0.2,
        "price": 500
    },
    "Воронка": {
        "description": "Артефакт в форме воронки. Значительно увеличивает шанс находок.",
        "bonus": "+20% к находкам",
        "bonus_type": "find_chance",
        "bonus_value": 20,
        "weight": 0.8,
        "price": 1200
    },
    "Слизь": {
        "description": "Скользкий артефакт. Восстанавливает здоровье.",
        "bonus": "+10 HP",
        "bonus_type": "health",
        "bonus_value": 10,
        "weight": 0.4,
        "price": 400
    },
    "Пыль": {
        "description": "Лёгкий артефакт, похожий на пыль. Помогает уклоняться.",
        "bonus": "+5% к уклонению",
        "bonus_type": "dodge",
        "bonus_value": 5,
        "weight": 0.1,
        "price": 550
    },
    "Фрагмент": {
        "description": "Осколок аномалии. Увеличивает силу.",
        "bonus": "+5 к силе",
        "bonus_type": "strength",
        "bonus_value": 5,
        "weight": 0.6,
        "price": 700
    }
}

# Приборы
DEVICES = {
    "Детектор аномалий": {
        "description": "Прибор для обнаружения аномалий. Показывает тип и опасность.",
        "bonus": "Видишь аномалии, +10% шанс артефакта",
        "effect": "anomaly_detector",
        "weight": 0.5,
        "price": 800
    },
    "Фонарик": {
        "description": "Источник света в темноте.",
        "bonus": "+5% к находкам ночью",
        "effect": "flashlight",
        "weight": 0.3,
        "price": 200
    },
    "Компас": {
        "description": "Компас для навигации.",
        "bonus": "+5% к находкам",
        "effect": "compass",
        "weight": 0.1,
        "price": 150
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
    if equipped_device and equipped_device.lower() in ['детектор аномалий', 'детектор']:
        return True
    
    # Проверяем в инвентаре
    player.inventory.reload()
    for item in player.inventory.other:
        if 'детектор' in item['name'].lower():
            return True
    
    return False
