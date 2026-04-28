"""
Константы и перечисления для игры
"""
from enum import Enum


# === Локации ===
class LocationType(Enum):
    CITY = "город"
    KPP = "кпп"
    HOSPITAL = "больница"
    BLACK_MARKET = "черный рынок"
    SHELTER = "убежище"
    INVENTORY = "инвентарь"
    MILITARY_ROAD = "дорога_военная_часть"
    NII_ROAD = "дорога_нии"
    INFECTED_FOREST = "дорога_зараженный_лес"
    MILITARY_BASE = "военная_часть"
    NII_MAIN_BUILDING = "главный_корпус_нии"
    INFECTED_FOREST_DEEP = "зараженный_лес"


# === Разделы инвентаря ===
class InventorySection(Enum):
    WEAPONS = "weapons"
    ARMOR = "armor"
    BACKPACKS = "backpacks"
    ARTIFACTS = "artifacts"
    OTHER = "other"


# === Категории предметов ===
class ItemCategory(Enum):
    WEAPONS = "weapons"
    ARMOR = "armor"
    BACKPACKS = "backpacks"
    ARTIFACTS = "artifacts"
    RARE_ARTIFACTS = "rare_artifacts"
    OTHER = "other"
    CONSUMABLES = "consumables"
    TRASH = "trash"


# === Команды для маппинга ===
COMMANDS = {
    # Навигация
    'начать': 'start',
    'старт': 'start',
    '/start': 'start',
    '/help': 'start',
    
    # Локации
    'город': 'location:город',
    'больница': 'location:больница',
    'черный рынок': 'location:черный рынок',
    'кпп': 'location:кпп',
    'убежище': 'location:убежище',
    'инвентарь': 'inventory_open',
    'карта': 'map_open',
    
    # Дороги
    'дорога на военную часть': 'location:дорога_военная_часть',
    'дорога на нии': 'location:дорога_нии',
    'дорога на зараженный лес': 'location:дорога_зараженный_лес',
    'военная часть': 'location:военная_часть',
    'главный корпус нии': 'location:главный_корпус_нии',
    'зараженный лес': 'location:зараженный_лес',
    
    # Статус
    'статус': 'status',
    '/status': 'status',
    
    # Инвентарь - разделы
    'оружие': 'inventory_section:weapons',
    'броня': 'inventory_section:armor',
    'рюкзаки': 'inventory_section:backpacks',
    'артефакты': 'inventory_section:artifacts',
    'другое': 'inventory_section:other',
    
    # Инвентарь - действия
    'надеть рюкзак': 'equip_backpack',
    'снять рюкзак': 'unequip_backpack',
    'использовать': 'use_item',
    'выпить': 'use_item',
    'съесть': 'use_item',
    'купить': 'buy',
    'продать': 'sell',
    
    # Артефакты
    'купить слот': 'buy_artifact_slot',
    'купить слот артефакта': 'buy_artifact_slot',
    'экипировка': 'show_equipped',
    'инструкция': 'show_artifact_help',
    
    # Локации - действия
    'спать': 'sleep',
    'поспать': 'sleep',
    'отдохнуть': 'sleep',
    'лечиться': 'heal',
    'лечение': 'heal',
    'подтвердить лечение': 'heal_confirm',
    'отмена лечения': 'heal_cancel',
    'отменить лечение': 'heal_cancel',
    'исследовать': 'explore',
    'говорить': 'talk',
    'диалог': 'talk',
    'крафт': 'craft_menu',
    'верстак': 'craft_menu',
    'рецепты': 'craft_menu',
    'скрафтить': 'craft_build',
    'шкаф': 'storage_menu',
    'хранилище': 'storage_menu',
    'в шкаф': 'storage_put',
    'из шкафа': 'storage_take',
    
    # Диалог
    'покинуть диалог': 'exit_dialog',
    'покинуть': 'exit_dialog',
    
    # Перемещение
    'в город': 'move:город',
    'в кпп': 'move:кпп',
    'назад': 'back',
    'выйти': 'back',
    'выйти из': 'back',
    
    # Бой
    'атаковать': 'combat_attack',
    'атака': 'combat_attack',
    'убежать': 'combat_flee',
    'бежать': 'combat_flee',
    'выстрел': 'combat_weapon',
    'очередь': 'combat_weapon',
    'разрез': 'combat_weapon',
    'укрытие': 'combat_cover',
    'укрыться': 'combat_cover',
}


# === Исследовательские локации ===
RESEARCH_LOCATIONS = [
    LocationType.MILITARY_ROAD.value,
    LocationType.MILITARY_BASE.value,
    LocationType.NII_ROAD.value,
    LocationType.NII_MAIN_BUILDING.value,
    LocationType.INFECTED_FOREST.value,
    LocationType.INFECTED_FOREST_DEEP.value,
]

# === Дроп предметов по локациям ===
# Процент используется как вес/шанс выбора конкретного предмета в этой локации.
# Если локация не указана для предмета -> шанс считается 0.
ITEM_CATEGORY_DROP_CHANCES_BY_LOCATION = {
    LocationType.MILITARY_ROAD.value: {
        "weapons": 16,
        "armor": 14,
        "meds": 8,
        "food": 6,
        "consumables": 10,
        "other": 8,
        "trash": 34,
        "artifacts": 4,
        "rare_weapons": 4,
        "rare_armor": 3,
        "resources": 4,
    },
    LocationType.NII_ROAD.value: {
        "weapons": 10,
        "armor": 12,
        "meds": 14,
        "food": 8,
        "consumables": 10,
        "other": 12,
        "trash": 30,
        "artifacts": 12,
        "rare_weapons": 2,
        "rare_armor": 2,
        "resources": 4,
    },
    LocationType.INFECTED_FOREST.value: {
        "weapons": 10,
        "armor": 9,
        "meds": 8,
        "food": 8,
        "consumables": 12,
        "other": 8,
        "trash": 35,
        "artifacts": 12,
        "rare_weapons": 3,
        "rare_armor": 2,
        "resources": 6,
    },
    LocationType.MILITARY_BASE.value: {
        "weapons": 20,
        "armor": 18,
        "meds": 7,
        "food": 5,
        "consumables": 10,
        "other": 8,
        "trash": 24,
        "artifacts": 4,
        "rare_weapons": 6,
        "rare_armor": 5,
        "resources": 6,
    },
    LocationType.NII_MAIN_BUILDING.value: {
        "weapons": 8,
        "armor": 10,
        "meds": 16,
        "food": 6,
        "consumables": 12,
        "other": 14,
        "trash": 24,
        "artifacts": 16,
        "rare_weapons": 2,
        "rare_armor": 2,
        "resources": 6,
    },
    LocationType.INFECTED_FOREST_DEEP.value: {
        "weapons": 8,
        "armor": 8,
        "meds": 7,
        "food": 7,
        "consumables": 12,
        "other": 8,
        "trash": 28,
        "artifacts": 16,
        "rare_weapons": 3,
        "rare_armor": 2,
        "resources": 10,
    },
}

# === Порог уровней по локациям (для дропа/скейла) ===
# Если локации нет в таблице — используем fallback: min=1, max=100.
LOCATION_LEVEL_THRESHOLDS = {
    LocationType.MILITARY_ROAD.value: {"min": 1, "max": 5},
    LocationType.NII_ROAD.value: {"min": 1, "max": 5},
    LocationType.INFECTED_FOREST.value: {"min": 3, "max": 7},
    LocationType.MILITARY_BASE.value: {"min": 5, "max": 10},
    LocationType.NII_MAIN_BUILDING.value: {"min": 5, "max": 10},
    LocationType.INFECTED_FOREST_DEEP.value: {"min": 5, "max": 10},
}

# === Баланс дропа по фарм-локациям ===
# Ограничивает "качество" выпадающих предметов на конкретной локации.
# Не влияет на доступность входа игрока в локацию.
LOCATION_DROP_BALANCE_RULES = {
    LocationType.MILITARY_ROAD.value: {
        "max_price": 5_000,
        "max_rarity": "rare",
    },
    LocationType.NII_ROAD.value: {
        "max_price": 3_000,
        "max_rarity": "rare",
    },
    LocationType.INFECTED_FOREST.value: {
        "max_price": 5_000,
        "max_rarity": "rare",
    },
    LocationType.MILITARY_BASE.value: {
        "max_price": 8_000,
        "max_rarity": "rare",
    },
    LocationType.NII_MAIN_BUILDING.value: {
        "max_price": 7_000,
        "max_rarity": "rare",
    },
    LocationType.INFECTED_FOREST_DEEP.value: {
        "max_price": 7_500,
        "max_rarity": "rare",
    },
}


# === Безопасные локации (укрытия от Выброса) ===
SAFE_LOCATIONS = [
    LocationType.CITY.value,
    LocationType.HOSPITAL.value,
    LocationType.SHELTER.value,
    LocationType.KPP.value,
    LocationType.BLACK_MARKET.value,
]

# === Опасные локации (Зона — урон от Выброса) ===
DANGEROUS_LOCATIONS = [
    LocationType.MILITARY_ROAD.value,
    LocationType.MILITARY_BASE.value,
    LocationType.NII_ROAD.value,
    LocationType.NII_MAIN_BUILDING.value,
    LocationType.INFECTED_FOREST.value,
    LocationType.INFECTED_FOREST_DEEP.value,
]


# === NPC-локации ===
NPC_LOCATIONS = {
    'кпп': ['военный', 'ученый'],
    'больница': ['медик'],
    'убежище': ['местный житель', 'наставник', 'дозиметрист'],
    'черный рынок': ['барыга'],
}


# === Набор новичка ===
NEWBIE_KIT_ITEMS = [
    ("ПМ", 1),                   # Оружие
    ("Кепка", 1),                # Базовый сет брони: голова
    ("Кожаная куртка", 1),       # Базовый сет брони: тело
    ("Джинсы", 1),               # Базовый сет брони: ноги
    ("Перчатки без пальцев", 1), # Базовый сет брони: руки
    ("Кеды", 1),                 # Базовый сет брони: обувь
    ("Аптечка", 1),              # Медицина
    ("Бинт", 1),                 # Медицина
    ("Вода", 1),                 # Вода
    ("Маленький мешочек", 1),    # Стартовый мешочек под гильзы
]
