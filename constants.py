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
    
    # Дороги
    'дорога на военную часть': 'location:дорога_военная_часть',
    'дорога на нии': 'location:дорога_нии',
    'дорога на зараженный лес': 'location:дорога_зараженный_лес',
    
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
    'исследовать': 'explore',
    'говорить': 'talk',
    'диалог': 'talk',
    
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
    LocationType.NII_ROAD.value,
    LocationType.INFECTED_FOREST.value,
]


# === NPC-локации ===
NPC_LOCATIONS = {
    'кпп': ['военный', 'ученый', 'барыга'],
    'убежище': ['местный житель', 'наставник'],
    'черный рынок': ['барыга'],
}


# === Набор новичка ===
NEWBIE_KIT_ITEMS = [
    ("ПМ", 1),              # Пистолет
    ("Кожаная куртка", 1),  # Броня
    ("Бинт", 3),            # Медицина
    ("Хлеб", 2),            # Еда
    ("Вода", 1),            # Вода
    ("Гильза", 10),         # Гильзы для старта
]

