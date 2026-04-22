"""
Система крафта предметов в убежище.
"""
from __future__ import annotations

from typing import Any

from infra import database


CRAFTING_XP_FLAG = "survival_crafting_xp"
CRAFTING_MAX_LEVEL = 10
CRAFTING_LEVEL_THRESHOLDS = {
    1: 0,
    2: 80,
    3: 180,
    4: 320,
    5: 500,
    6: 750,
    7: 1050,
    8: 1400,
    9: 1800,
    10: 2250,
}


# Рецепты только из актуального пула предметов.
CRAFT_RECIPES: list[dict[str, Any]] = [
    {
        "id": "stim_pack",
        "name": "Полевой стим-пак",
        "ingredients": [("Бинт", 1), ("Энергетик", 1)],
        "result": ("Стимулятор", 1),
        "required_level": 1,
        "xp_gain": 25,
        "description": "+50 HP, +20 энергии",
    },
    {
        "id": "field_ration",
        "name": "Полевой рацион",
        "ingredients": [("Хлеб", 1), ("Консервы", 1)],
        "result": ("Энергетический батончик", 1),
        "required_level": 1,
        "xp_gain": 20,
        "description": "+40 энергии",
    },
    {
        "id": "clean_water",
        "name": "Очищенная вода",
        "ingredients": [("Вода", 1), ("Антирад", 1)],
        "result": ("Чистая вода", 1),
        "required_level": 1,
        "xp_gain": 20,
        "description": "+30 HP и -10 радиации",
    },
    {
        "id": "science_medkit",
        "name": "Научная аптечка (сборка)",
        "ingredients": [("Аптечка", 1), ("Антидот", 1)],
        "result": ("Научная аптечка", 1),
        "required_level": 2,
        "xp_gain": 35,
        "description": "Восстанавливает 80% HP",
    },
    {
        "id": "combat_stim",
        "name": "Боевой стим",
        "ingredients": [("Стимулятор", 1), ("Лечебная трава", 1)],
        "result": ("Боевой стимулятор", 1),
        "required_level": 2,
        "xp_gain": 40,
        "description": "+80 HP, +50 энергии",
    },
    {
        "id": "dosimeter",
        "name": "Самодельный дозиметр",
        "ingredients": [("Пустая бутылка", 1), ("Медная проволока", 1)],
        "result": ("Дозиметр", 1),
        "required_level": 2,
        "xp_gain": 30,
        "description": "Прибор контроля радиации",
    },
    {
        "id": "shell_bundle",
        "name": "Пакет гильз",
        "ingredients": [("Гильзы", 1), ("Медная проволока", 1)],
        "result": ("Гильзы", 2),
        "required_level": 3,
        "xp_gain": 35,
        "description": "Упаковка патронных гильз",
    },
    {
        "id": "kolobok",
        "name": "Аномальный колобок",
        "ingredients": [("Капля", 1), ("Пружина", 1)],
        "result": ("Колобок", 1),
        "required_level": 4,
        "xp_gain": 60,
        "description": "Редкий артефакт",
    },
    {
        "id": "moonlight",
        "name": "Лунный свет",
        "ingredients": [("Выверт", 1), ("Батарейка", 1)],
        "result": ("Лунный свет", 1),
        "required_level": 5,
        "xp_gain": 75,
        "description": "Редкий артефакт",
    },
]


def get_crafting_level_by_xp(xp: int) -> int:
    safe_xp = max(0, int(xp or 0))
    level = 1
    for lvl in range(1, CRAFTING_MAX_LEVEL + 1):
        if safe_xp >= CRAFTING_LEVEL_THRESHOLDS[lvl]:
            level = lvl
    return level


def get_crafting_progress(vk_id: int) -> dict[str, int]:
    xp = int(database.get_user_flag(vk_id, CRAFTING_XP_FLAG, 0) or 0)
    level = get_crafting_level_by_xp(xp)
    next_level = min(CRAFTING_MAX_LEVEL, level + 1)
    next_threshold = CRAFTING_LEVEL_THRESHOLDS[next_level]
    current_threshold = CRAFTING_LEVEL_THRESHOLDS[level]
    return {
        "xp": xp,
        "level": level,
        "next_level": next_level,
        "current_threshold": current_threshold,
        "next_threshold": next_threshold,
    }


def add_crafting_xp(vk_id: int, amount: int) -> dict[str, int]:
    gained = max(0, int(amount or 0))
    old_xp = int(database.get_user_flag(vk_id, CRAFTING_XP_FLAG, 0) or 0)
    new_xp = old_xp + gained
    database.set_user_flag(vk_id, CRAFTING_XP_FLAG, new_xp)
    old_level = get_crafting_level_by_xp(old_xp)
    new_level = get_crafting_level_by_xp(new_xp)
    return {
        "old_xp": old_xp,
        "new_xp": new_xp,
        "old_level": old_level,
        "new_level": new_level,
        "gained": gained,
    }


def get_recipe_by_index(index: int) -> dict[str, Any] | None:
    if 1 <= index <= len(CRAFT_RECIPES):
        return CRAFT_RECIPES[index - 1]
    return None

