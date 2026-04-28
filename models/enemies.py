# Враги по локациям для системы исследования
import random


def get_weapon_type(weapon_name):
    """Определить тип оружия по названию"""
    if not weapon_name:
        return "нож"  # Без оружия - только нож

    weapon_lower = weapon_name.lower()

    # Пистолеты: ПМ, ТТ, Глок, Удав, ПММ, П-99, П-96, С-40П
    if "пистолет" in weapon_lower or "пм" in weapon_lower or "тт" in weapon_lower or \
       "глок" in weapon_lower or "удав" in weapon_lower:
        return "пистолет"

    # Автоматы: АК-74, АКС-74У, М4А1, АК-101, АК-105, ГРООС-35, АК-12
    elif "автомат" in weapon_lower or "ак-" in weapon_lower or "м4" in weapon_lower or \
         "гроос" in weapon_lower:
        return "автомат"

    # Снайперские винтовки: СВД, Винторез, С-98, Т-5000, ОСВ-96, Мосина, ВСК-100, Лось-7
    elif "свд" in weapon_lower or "винторез" in weapon_lower or "с-98" in weapon_lower or \
         "т-5000" in weapon_lower or "осв" in weapon_lower or "мосина" in weapon_lower or \
         "вск-100" in weapon_lower or "лось" in weapon_lower:
        return "снайперка"

    # Дробовики: ИЖ-27, Сайга-12, МР-153, Вепрь-12, Кострома, Бекас-Авто, Сайга-410
    elif "дробовик" in weapon_lower or "сайга" in weapon_lower or "иж-" in weapon_lower or \
         "мр-" in weapon_lower or "вепрь" in weapon_lower or "кострома" in weapon_lower or \
         "бекас" in weapon_lower:
        return "дробовик"

    # Пулемёты: ПКМ, РПК-74, Печенег, М240, М249, РПК-16, Корд (пулемёт)
    elif "пулемет" in weapon_lower or "пулемёт" in weapon_lower or "пкм" in weapon_lower or \
         "рпк" in weapon_lower or "печенег" in weapon_lower or "м240" in weapon_lower or \
         "м249" in weapon_lower:
        return "пулемет"

    # Ножи: Нож сталкера, Мачете, Нож разведчика, Штык-нож, Финка, Кинжал, Ятаган
    elif "нож" in weapon_lower or "мачете" in weapon_lower or "штык" in weapon_lower or \
         "финка" in weapon_lower or "кинжал" in weapon_lower or "ятаган" in weapon_lower or \
         "knife" in weapon_lower:
        return "нож"

    else:
        return "нож"  # По умолчанию


# Действия оружия в бою
WEAPON_ACTIONS = {
    "пистолет": {
        "name": "🔫 Выстрел",
        "shots": 1,
        "damage_multiplier": 1.0,
        "miss_chance": 10,  # 10% шанс промаха
        "special": None
    },
    "автомат": {
        "name": "📍 Очередь",
        "shots": "2-5",  # От 2 до 5 выстрелов
        "damage_multiplier": 1.0,
        "miss_chance": 15,
        "special": None
    },
    "снайперка": {
        "name": "🎯 Выстрел",
        "shots": 1,
        "damage_multiplier": 1.5,  # 50% бонус к урону (высокая точность)
        "miss_chance": 5,  # Маленький шанс промаха
        "special": "headshot"  # Шанс на убойный выстрел
    },
    "дробовик": {
        "name": "💥 Выстрел",
        "shots": 1,
        "damage_multiplier": 0.2,  # 20% от атаки за каждую дробинку
        "miss_chance": 35,  # Большой шанс промаха
        "special": "scatter"  # Дробь
    },
    "пулемет": {
        "name": "📍 Очередь",
        "shots": "2-10",
        "damage_multiplier": 1.0,
        "miss_chance": 20,
        "special": None
    },
    "нож": {
        "name": "🔪 Разрез",
        "shots": 1,
        "damage_multiplier": 1.0,
        "miss_chance": 5,  # Маленький шанс промаха
        "special": "bleed"  # Кровотечение
    }
}


ENEMIES = {
    "дорога_военная_часть": [
        {
            "name": "🔫 Военный рейдер",
            "description": "Бывшие солдаты, перешедшие на сторону бандитов. Вооружены до зубов.",
            "hp": 100,
            "damage": 25,
            "chance": 35
        },
        {
            "name": "💀 Зомби-солдат",
            "description": "Погибшие военные, вернувшиеся к жизни. Опасны вблизи.",
            "hp": 80,
            "damage": 20,
            "chance": 30
        },
        {
            "name": "🤖 Военный дрон",
            "description": "Автономный дрон-убийца, патрулирующий территорию.",
            "hp": 60,
            "damage": 30,
            "chance": 20
        },
        {
            "name": "🧟 Мутировавший охранник",
            "description": "Охранник военной части, заражённый вирусом.",
            "hp": 120,
            "damage": 35,
            "chance": 15
        }
    ],
    "военная_часть": [
        {
            "name": "🎖️ Дежурный патруль",
            "description": "Остатки гарнизона держат внутренний периметр и стреляют без предупреждения.",
            "hp": 120,
            "damage": 30,
            "chance": 34
        },
        {
            "name": "🤖 Сторожевой дрон",
            "description": "Дрон скользит между казармами, цепляя прожектором каждый проход.",
            "hp": 85,
            "damage": 34,
            "chance": 24
        },
        {
            "name": "💀 Зомби-сержант",
            "description": "Бывший командир караула всё ещё ведёт свой пост по мёртвому распорядку.",
            "hp": 115,
            "damage": 28,
            "chance": 24
        },
        {
            "name": "🔫 Военный мародёр",
            "description": "Опытный стрелок, который разбирает склады и не любит свидетелей.",
            "hp": 100,
            "damage": 32,
            "chance": 18
        }
    ],
    "дорога_нии": [
        {
            "name": "🧪 Лабораторный мутант",
            "description": "Результат неудачных экспериментов. Неустойчив, но опасен.",
            "hp": 70,
            "damage": 20,
            "chance": 35
        },
        {
            "name": "👨‍🔬 Охранник НИИ",
            "description": "Вооружённая охрана института. Профессионально стреляет.",
            "hp": 110,
            "damage": 30,
            "chance": 25
        },
        {
            "name": "☢️ Радиоактивный учёный",
            "description": "Исследователь, заражённый радиацией. Источает смертоносное излучение.",
            "hp": 90,
            "damage": 25,
            "chance": 25
        },
        {
            "name": "🦠 Биологическая аномалия",
            "description": "Сгусток опасного вируса в человеческом обличье.",
            "hp": 50,
            "damage": 40,
            "chance": 15
        }
    ],
    "главный_корпус_нии": [
        {
            "name": "🧪 Сорвавшийся образец",
            "description": "Экспериментальный мутант мечется по лаборатории и реагирует на тепло.",
            "hp": 95,
            "damage": 28,
            "chance": 32
        },
        {
            "name": "☢️ Облучённый техник",
            "description": "Техник в порванном защитном костюме тащит за собой шлейф радиации.",
            "hp": 100,
            "damage": 30,
            "chance": 26
        },
        {
            "name": "👨‍🔬 Охрана корпуса",
            "description": "Автоматчик из внутренней охраны НИИ, привыкший стрелять в узких коридорах.",
            "hp": 120,
            "damage": 34,
            "chance": 24
        },
        {
            "name": "🧠 Пси-искажение",
            "description": "Не человек и не тварь: сгусток чужой памяти, который давит на сознание.",
            "hp": 80,
            "damage": 38,
            "chance": 18
        }
    ],
    "дорога_зараженный_лес": [
        {
            "name": "🐺 Мутант-волк",
            "description": "Стая волков-мутантов. Охотятся группой.",
            "hp": 150,
            "damage": 35,
            "chance": 30
        },
        {
            "name": "🌿 Аномальный сталкер",
            "description": "Человек, потерявший рассудок в аномальном лесу. Бьётся в конвульсиях.",
            "hp": 80,
            "damage": 20,
            "chance": 25
        },
        {
            "name": "☠️ Химера",
            "description": "Ужасное существо из плоти разных животных. Смертельно опасно.",
            "hp": 200,
            "damage": 50,
            "chance": 20
        },
        {
            "name": "🦇 Летающий мутант",
            "description": "Гигантские летучие мыши. Нападают сверху.",
            "hp": 60,
            "damage": 15,
            "chance": 15
        },
        {
            "name": "🍄 Растение-убийца",
            "description": "Аномальное растение, захватившее тело выжившего.",
            "hp": 100,
            "damage": 25,
            "chance": 10
        }
    ]
    ,
    "зараженный_лес": [
        {
            "name": "🐺 Матёрый мутант-волк",
            "description": "Крупный вожак малой стаи, быстрый и упрямый.",
            "hp": 170,
            "damage": 38,
            "chance": 30
        },
        {
            "name": "🦴 Лесная химера",
            "description": "Химера из глубины чащи, привыкшая нападать из-за стволов.",
            "hp": 220,
            "damage": 52,
            "chance": 20
        },
        {
            "name": "🍄 Споровый носитель",
            "description": "Мутировавшее тело, из которого вырываются облака едких спор.",
            "hp": 110,
            "damage": 30,
            "chance": 22
        },
        {
            "name": "🌿 Аномальный охотник",
            "description": "Сталкер, давно потерявший себя и слившийся с лесной охотой.",
            "hp": 105,
            "damage": 29,
            "chance": 18
        },
        {
            "name": "🦇 Рой летучих мутантов",
            "description": "Несколько мелких тварей бьют с воздуха и рвут открытые места.",
            "hp": 90,
            "damage": 24,
            "chance": 10
        }
    ]
}


def get_enemy_for_location(location_id):
    """Получить случайного врага для локации"""
    import random
    
    if location_id not in ENEMIES:
        return None
    
    enemies = ENEMIES[location_id]
    total_chance = sum(e["chance"] for e in enemies)
    roll = random.randint(1, total_chance)
    
    current = 0
    for enemy in enemies:
        current += enemy["chance"]
        if roll <= current:
            return enemy
    
    return enemies[0]  # Фоллбек


def get_enemy_by_type(enemy_type: str):
    """Получить врага по типу (mutant, bandit, military)"""
    import random

    # Все враги из всех локаций
    all_enemies = []
    for location_enemies in ENEMIES.values():
        all_enemies.extend(location_enemies)

    # Фильтруем по типу
    if enemy_type == "mutant":
        filtered = [e for e in all_enemies if "mutant" in e["name"].lower() or "плоть" in e["name"].lower() or "кабан" in e["name"].lower() or "слеп" in e["name"].lower()]
    elif enemy_type == "bandit":
        filtered = [e for e in all_enemies if "бандит" in e["name"].lower()]
    elif enemy_type == "military":
        filtered = [e for e in all_enemies if "военн" in e["name"].lower()]
    else:
        filtered = all_enemies

    if not filtered:
        return random.choice(all_enemies) if all_enemies else None

    return random.choice(filtered)
