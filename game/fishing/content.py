"""Fishing content tables and data models.

Keep expandable content here: spots, gear, bait, species, bonus drops,
cooking recipes, and NPC orders. Runtime mechanics live in service.py.
"""
from __future__ import annotations

from dataclasses import dataclass

TOURBASE_LOCATION = "турбаза_лучик"
LAKE_LOCATION = "озеро"
FISHING_STATE_KEY = "fishing_state"
FISHING_DURATION_SECONDS = 4 * 60
FISH_LOCKER_CAPACITY = 80


@dataclass(frozen=True)
class FishingSpot:
    id: str
    label: str
    energy_cost: int
    risk: int
    score_bonus: int
    rare_bonus: int
    description: str


@dataclass(frozen=True)
class FishingGear:
    name: str
    label: str
    tier: int
    junk_resist: int = 0
    rare_bonus: int = 0
    hazard_resist: int = 0
    deep_bonus: int = 0
    anomaly_bonus: int = 0
    bonus_drop_bonus: int = 0


@dataclass(frozen=True)
class FishingBait:
    name: str
    label: str
    junk_resist: int = 0
    rare_bonus: int = 0
    bonus_drop_bonus: int = 0


@dataclass(frozen=True)
class FishSpecies:
    name: str
    tier: str
    spots: tuple[str, ...]
    weight_min: float
    weight_max: float
    price_per_kg_min: int
    price_per_kg_max: int
    xp: int
    bait_bonus: tuple[str, ...] = ()


SPOTS: dict[str, FishingSpot] = {
    "shore": FishingSpot(
        id="shore",
        label="Береговая снасть",
        energy_cost=7,
        risk=3,
        score_bonus=-5,
        rare_bonus=-4,
        description="безопасная ловля с мелким уловом",
    ),
    "deep": FishingSpot(
        id="deep",
        label="Глубокий заброс",
        energy_cost=11,
        risk=7,
        score_bonus=5,
        rare_bonus=3,
        description="лучше улов, но снасть чаще цепляет мусор",
    ),
    "anomaly": FishingSpot(
        id="anomaly",
        label="Аномальная заводь",
        energy_cost=16,
        risk=15,
        score_bonus=12,
        rare_bonus=10,
        description="редкие находки и риск радиации",
    ),
}

FALLBACK_GEAR = FishingGear(
    name="",
    label="Леска с крючком",
    tier=0,
    junk_resist=0,
    rare_bonus=0,
    hazard_resist=0,
)

GEAR: tuple[FishingGear, ...] = (
    FishingGear(
        name="Старая удочка",
        label="Старая удочка",
        tier=1,
        junk_resist=4,
        rare_bonus=2,
        hazard_resist=1,
        deep_bonus=1,
    ),
    FishingGear(
        name="Складная удочка",
        label="Складная удочка",
        tier=2,
        junk_resist=8,
        rare_bonus=3,
        hazard_resist=2,
    ),
    FishingGear(
        name="Армированная удочка",
        label="Армированная удочка",
        tier=3,
        junk_resist=6,
        rare_bonus=5,
        hazard_resist=3,
        deep_bonus=6,
    ),
    FishingGear(
        name="Изолированная удочка",
        label="Изолированная удочка",
        tier=4,
        junk_resist=7,
        rare_bonus=6,
        hazard_resist=7,
        anomaly_bonus=5,
    ),
    FishingGear(
        name="Резонансная удочка",
        label="Резонансная удочка",
        tier=5,
        junk_resist=10,
        rare_bonus=10,
        hazard_resist=6,
        deep_bonus=4,
        anomaly_bonus=8,
        bonus_drop_bonus=4,
    ),
)

BAITS: tuple[FishingBait, ...] = (
    FishingBait(
        name="Черви",
        label="Черви",
        junk_resist=3,
        rare_bonus=2,
        bonus_drop_bonus=1,
    ),
    FishingBait(
        name="Хлебный мякиш",
        label="Хлебный мякиш",
        junk_resist=2,
        rare_bonus=-1,
    ),
    FishingBait(
        name="Живая наживка",
        label="Живая наживка",
        junk_resist=4,
        rare_bonus=5,
        bonus_drop_bonus=1,
    ),
    FishingBait(
        name="Пахучая прикормка",
        label="Пахучая прикормка",
        junk_resist=8,
        rare_bonus=3,
    ),
    FishingBait(
        name="Аномальная наживка",
        label="Аномальная наживка",
        junk_resist=3,
        rare_bonus=9,
        bonus_drop_bonus=5,
    ),
)

LUCHIK_SHOP_ITEMS: tuple[str, ...] = (
    "Хлебный мякиш",
    "Черви",
    "Живая наживка",
    "Пахучая прикормка",
    "Аномальная наживка",
    "Старая удочка",
    "Складная удочка",
    "Армированная удочка",
    "Изолированная удочка",
    "Резонансная удочка",
)

LUCHIK_ROD_UPGRADES = {
    "Складная удочка": {
        "requires": [("Старая удочка", 1)],
        "note": "нужна старая удочка как основа",
    },
    "Армированная удочка": {
        "requires": [("Складная удочка", 1), ("Затонувший контейнер", 1)],
        "note": "нужна складная удочка и редкая деталь со дна",
    },
    "Изолированная удочка": {
        "requires": [("Армированная удочка", 1), ("Аномальная чешуя", 3), ("Затонувший контейнер", 1)],
        "note": "нужна армированная удочка и аномальные материалы",
    },
    "Резонансная удочка": {
        "requires": [("Изолированная удочка", 1), ("Аномальная чешуя", 8), ("Затонувший контейнер", 3)],
        "note": "долгий апгрейд для тех, кто реально живёт у озера",
    },
}


JUNK_CATCHES = {
    "junk": [
        ("Рваная леска", [("Рваная леска", 1)], 35),
        ("Мокрый хлам", [("Мокрый хлам", 1)], 40),
    ],
}

FISH_SPECIES: tuple[FishSpecies, ...] = (
    FishSpecies('Серебристая плотва', 'common', ('shore', 'deep'), 0.12, 0.55, 95, 140, 70, ('Хлебный мякиш', 'Черви')),
    FishSpecies('Пятнистый окунь', 'common', ('shore', 'deep'), 0.18, 0.9, 105, 155, 80, ('Черви', 'Живая наживка')),
    FishSpecies('Старый карась', 'common', ('shore',), 0.25, 1.4, 80, 130, 75, ('Хлебный мякиш', 'Пахучая прикормка')),
    FishSpecies('Ржавая уклейка', 'common', ('shore',), 0.05, 0.18, 70, 115, 45, ('Хлебный мякиш',)),
    FishSpecies('Камышовый ёрш', 'common', ('shore',), 0.08, 0.28, 75, 120, 50, ('Черви',)),
    FishSpecies('Синежабрый пескарь', 'common', ('shore', 'anomaly'), 0.04, 0.16, 110, 170, 60, ('Черви', 'Аномальная наживка')),
    FishSpecies('Турбазный лещ', 'common', ('shore', 'deep'), 0.45, 1.8, 90, 135, 85, ('Пахучая прикормка',)),
    FishSpecies('Тяжелый карп', 'uncommon', ('deep', 'shore'), 1.2, 5.5, 125, 185, 125, ('Пахучая прикормка',)),
    FishSpecies('Слепая щука', 'uncommon', ('deep', 'anomaly'), 0.9, 4.2, 160, 240, 140, ('Живая наживка', 'Аномальная наживка')),
    FishSpecies('Чёрный линь', 'uncommon', ('deep',), 0.7, 3.4, 135, 210, 115, ('Черви', 'Пахучая прикормка')),
    FishSpecies('Глубинный судак', 'uncommon', ('deep',), 1.0, 4.8, 175, 260, 150, ('Живая наживка',)),
    FishSpecies('Мутный сомик', 'uncommon', ('deep', 'anomaly'), 1.5, 7.0, 145, 230, 155, ('Живая наживка',)),
    FishSpecies('Белоглазый налим', 'uncommon', ('deep', 'anomaly'), 0.8, 3.2, 180, 275, 150, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Электрический угорь', 'rare', ('anomaly',), 0.6, 2.4, 360, 560, 210, ('Аномальная наживка',)),
    FishSpecies('Стеклянная форель', 'rare', ('anomaly', 'deep'), 0.35, 1.3, 420, 680, 220, ('Аномальная наживка',)),
    FishSpecies('Пси-карась', 'rare', ('anomaly',), 0.4, 1.9, 380, 620, 200, ('Аномальная наживка', 'Хлебный мякиш')),
    FishSpecies('Тихий хищник', 'rare', ('deep', 'anomaly'), 1.8, 6.5, 300, 480, 230, ('Живая наживка', 'Аномальная наживка')),
    FishSpecies('Зеркальный карп', 'rare', ('deep',), 2.0, 8.0, 260, 430, 225, ('Пахучая прикормка',)),
    FishSpecies('Ртутная щука', 'rare', ('anomaly',), 1.1, 5.2, 440, 720, 260, ('Аномальная наживка',)),
    FishSpecies('Старый донный сом', 'rare', ('deep',), 4.0, 18.0, 220, 380, 280, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Малая плотва', 'common', ('shore',), 0.22, 0.83, 81, 116, 64, ('Живая наживка',)),
    FishSpecies('Малый окунь', 'common', ('shore', 'deep'), 0.04, 0.83, 89, 133, 70, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Малый карась', 'common', ('shore',), 0.07, 1.04, 97, 150, 76, ('Аномальная наживка',)),
    FishSpecies('Малая уклейка', 'common', ('shore', 'deep'), 0.1, 1.25, 105, 167, 82, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Малый ёрш', 'common', ('shore',), 0.13, 0.38, 113, 184, 40, ('Хлебный мякиш',)),
    FishSpecies('Малый пескарь', 'common', ('shore', 'deep'), 0.16, 0.59, 121, 156, 46, ('Черви',)),
    FishSpecies('Малый лещ', 'common', ('shore',), 0.19, 0.8, 129, 173, 52, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Малый карп', 'common', ('shore', 'deep'), 0.22, 1.01, 65, 118, 58, ('Пахучая прикормка',)),
    FishSpecies('Малый линь', 'common', ('shore',), 0.04, 1.01, 73, 135, 64, ('Живая наживка',)),
    FishSpecies('Малый голавль', 'common', ('shore', 'deep'), 0.07, 1.22, 81, 152, 70, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Малый язь', 'common', ('shore',), 0.1, 0.35, 89, 124, 76, ('Аномальная наживка',)),
    FishSpecies('Малая краснопёрка', 'common', ('shore', 'deep'), 0.13, 0.56, 97, 141, 82, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Малая густера', 'common', ('shore',), 0.16, 0.77, 105, 158, 40, ('Хлебный мякиш',)),
    FishSpecies('Малый налим', 'common', ('shore', 'deep'), 0.19, 0.98, 113, 175, 46, ('Черви',)),
    FishSpecies('Малый судак', 'common', ('shore',), 0.22, 1.19, 121, 192, 52, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Малый сомик', 'common', ('shore', 'deep'), 0.04, 1.19, 129, 164, 58, ('Пахучая прикормка',)),
    FishSpecies('Малая щука', 'common', ('shore',), 0.07, 0.32, 65, 109, 64, ('Живая наживка',)),
    FishSpecies('Малая форель', 'common', ('shore', 'deep'), 0.1, 0.53, 73, 126, 70, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Малый угорь', 'common', ('shore',), 0.13, 0.74, 81, 143, 76, ('Аномальная наживка',)),
    FishSpecies('Малый бычок', 'common', ('shore', 'deep'), 0.16, 0.95, 89, 160, 82, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Малый подлещик', 'common', ('shore',), 0.19, 1.16, 97, 132, 40, ('Хлебный мякиш',)),
    FishSpecies('Малый синец', 'common', ('shore', 'deep'), 0.22, 1.37, 105, 149, 46, ('Черви',)),
    FishSpecies('Малая чехонь', 'common', ('shore',), 0.04, 0.29, 113, 166, 52, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Малый вьюн', 'common', ('shore', 'deep'), 0.07, 0.5, 121, 183, 58, ('Пахучая прикормка',)),
    FishSpecies('Малая щиповка', 'common', ('shore',), 0.1, 0.71, 129, 200, 64, ('Живая наживка',)),
    FishSpecies('Малая верховка', 'common', ('shore', 'deep'), 0.13, 0.92, 65, 100, 70, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Малый жерех', 'common', ('shore',), 0.16, 1.13, 73, 117, 76, ('Аномальная наживка',)),
    FishSpecies('Малый ротан', 'common', ('shore', 'deep'), 0.19, 1.34, 81, 134, 82, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Малый сазан', 'common', ('shore',), 0.22, 0.47, 89, 151, 40, ('Хлебный мякиш',)),
    FishSpecies('Малый омутник', 'common', ('shore', 'deep'), 0.04, 0.47, 97, 168, 46, ('Черви',)),
    FishSpecies('Малый камнекус', 'common', ('shore',), 0.07, 0.68, 105, 140, 52, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Малый илохвост', 'common', ('shore', 'deep'), 0.1, 0.89, 113, 157, 58, ('Пахучая прикормка',)),
    FishSpecies('Малый водомер', 'common', ('shore',), 0.13, 1.1, 121, 174, 64, ('Живая наживка',)),
    FishSpecies('Малый коряжник', 'common', ('shore', 'deep'), 0.16, 1.31, 129, 191, 70, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Малый мохоспин', 'common', ('shore',), 0.19, 0.44, 65, 136, 76, ('Аномальная наживка',)),
    FishSpecies('Малый желтоплав', 'common', ('shore', 'deep'), 0.22, 0.65, 73, 108, 82, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Малый синепёр', 'common', ('shore',), 0.04, 0.65, 81, 125, 40, ('Хлебный мякиш',)),
    FishSpecies('Малый сероспин', 'common', ('shore', 'deep'), 0.07, 0.86, 89, 142, 46, ('Черви',)),
    FishSpecies('Малый пятноглаз', 'common', ('shore',), 0.1, 1.07, 97, 159, 52, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Малый тихобрюх', 'common', ('shore', 'deep'), 0.13, 1.28, 105, 176, 58, ('Пахучая прикормка',)),
    FishSpecies('Береговая плотва', 'common', ('shore',), 0.16, 0.41, 113, 148, 64, ('Живая наживка',)),
    FishSpecies('Береговой окунь', 'common', ('shore', 'deep'), 0.19, 0.62, 121, 165, 70, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Береговой карась', 'common', ('shore',), 0.22, 0.83, 129, 182, 76, ('Аномальная наживка',)),
    FishSpecies('Береговая уклейка', 'common', ('shore', 'deep'), 0.04, 0.83, 65, 127, 82, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Береговой ёрш', 'common', ('shore',), 0.07, 1.04, 73, 144, 40, ('Хлебный мякиш',)),
    FishSpecies('Береговой пескарь', 'common', ('shore', 'deep'), 0.1, 1.25, 81, 116, 46, ('Черви',)),
    FishSpecies('Береговой лещ', 'common', ('shore',), 0.13, 0.38, 89, 133, 52, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Береговой карп', 'common', ('shore', 'deep'), 0.16, 0.59, 97, 150, 58, ('Пахучая прикормка',)),
    FishSpecies('Береговой линь', 'common', ('shore',), 0.19, 0.8, 105, 167, 64, ('Живая наживка',)),
    FishSpecies('Береговой голавль', 'common', ('shore', 'deep'), 0.22, 1.01, 113, 184, 70, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Береговой язь', 'common', ('shore',), 0.04, 1.01, 121, 156, 76, ('Аномальная наживка',)),
    FishSpecies('Береговая краснопёрка', 'common', ('shore', 'deep'), 0.07, 1.22, 129, 173, 82, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Береговая густера', 'common', ('shore',), 0.1, 0.35, 65, 118, 40, ('Хлебный мякиш',)),
    FishSpecies('Береговой налим', 'common', ('shore', 'deep'), 0.13, 0.56, 73, 135, 46, ('Черви',)),
    FishSpecies('Береговой судак', 'common', ('shore',), 0.16, 0.77, 81, 152, 52, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Береговой сомик', 'common', ('shore', 'deep'), 0.19, 0.98, 89, 124, 58, ('Пахучая прикормка',)),
    FishSpecies('Береговая щука', 'common', ('shore',), 0.22, 1.19, 97, 141, 64, ('Живая наживка',)),
    FishSpecies('Береговая форель', 'common', ('shore', 'deep'), 0.04, 1.19, 105, 158, 70, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Береговой угорь', 'common', ('shore',), 0.07, 0.32, 113, 175, 76, ('Аномальная наживка',)),
    FishSpecies('Береговой бычок', 'common', ('shore', 'deep'), 0.1, 0.53, 121, 192, 82, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Береговой подлещик', 'common', ('shore',), 0.13, 0.74, 129, 164, 40, ('Хлебный мякиш',)),
    FishSpecies('Береговой синец', 'common', ('shore', 'deep'), 0.16, 0.95, 65, 109, 46, ('Черви',)),
    FishSpecies('Береговая чехонь', 'common', ('shore',), 0.19, 1.16, 73, 126, 52, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Береговой вьюн', 'common', ('shore', 'deep'), 0.22, 1.37, 81, 143, 58, ('Пахучая прикормка',)),
    FishSpecies('Береговая щиповка', 'common', ('shore',), 0.04, 0.29, 89, 160, 64, ('Живая наживка',)),
    FishSpecies('Береговая верховка', 'common', ('shore', 'deep'), 0.07, 0.5, 97, 132, 70, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Береговой жерех', 'common', ('shore',), 0.1, 0.71, 105, 149, 76, ('Аномальная наживка',)),
    FishSpecies('Береговой ротан', 'common', ('shore', 'deep'), 0.13, 0.92, 113, 166, 82, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Береговой сазан', 'common', ('shore',), 0.16, 1.13, 121, 183, 40, ('Хлебный мякиш',)),
    FishSpecies('Береговой омутник', 'common', ('shore', 'deep'), 0.19, 1.34, 129, 200, 46, ('Черви',)),
    FishSpecies('Береговой камнекус', 'common', ('shore',), 0.22, 0.47, 65, 100, 52, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Береговой илохвост', 'common', ('shore', 'deep'), 0.04, 0.47, 73, 117, 58, ('Пахучая прикормка',)),
    FishSpecies('Береговой водомер', 'common', ('shore',), 0.07, 0.68, 81, 134, 64, ('Живая наживка',)),
    FishSpecies('Береговой коряжник', 'common', ('shore', 'deep'), 0.1, 0.89, 89, 151, 70, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Береговой мохоспин', 'common', ('shore',), 0.13, 1.1, 97, 168, 76, ('Аномальная наживка',)),
    FishSpecies('Береговой желтоплав', 'common', ('shore', 'deep'), 0.16, 1.31, 105, 140, 82, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Береговой синепёр', 'common', ('shore',), 0.19, 0.44, 113, 157, 40, ('Хлебный мякиш',)),
    FishSpecies('Береговой сероспин', 'common', ('shore', 'deep'), 0.22, 0.65, 121, 174, 46, ('Черви',)),
    FishSpecies('Береговой пятноглаз', 'common', ('shore',), 0.04, 0.65, 129, 191, 52, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Береговой тихобрюх', 'common', ('shore', 'deep'), 0.07, 0.86, 65, 136, 58, ('Пахучая прикормка',)),
    FishSpecies('Светлая плотва', 'common', ('shore',), 0.1, 1.07, 73, 108, 64, ('Живая наживка',)),
    FishSpecies('Светлый окунь', 'common', ('shore', 'deep'), 0.13, 1.28, 81, 125, 70, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Светлый карась', 'common', ('shore',), 0.16, 0.41, 89, 142, 76, ('Аномальная наживка',)),
    FishSpecies('Крупная плотва', 'uncommon', ('shore', 'deep'), 0.91, 3.21, 163, 228, 131, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Крупный окунь', 'uncommon', ('deep',), 1.05, 3.9, 175, 255, 140, ('Пахучая прикормка',)),
    FishSpecies('Крупный карась', 'uncommon', ('deep', 'anomaly'), 1.19, 4.59, 187, 282, 149, ('Живая наживка',)),
    FishSpecies('Крупная уклейка', 'uncommon', ('shore', 'deep'), 1.33, 5.28, 199, 309, 158, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Крупный ёрш', 'uncommon', ('deep',), 1.47, 5.97, 211, 336, 167, ('Аномальная наживка',)),
    FishSpecies('Крупный пескарь', 'uncommon', ('deep', 'anomaly'), 1.61, 6.66, 223, 363, 176, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Крупный лещ', 'uncommon', ('shore', 'deep'), 0.35, 1.55, 115, 180, 95, ('Хлебный мякиш',)),
    FishSpecies('Крупный карп', 'uncommon', ('deep',), 0.49, 2.24, 127, 207, 104, ('Черви',)),
    FishSpecies('Крупный линь', 'uncommon', ('deep', 'anomaly'), 0.63, 2.93, 139, 234, 113, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Крупный голавль', 'uncommon', ('shore', 'deep'), 0.77, 3.62, 151, 261, 122, ('Пахучая прикормка',)),
    FishSpecies('Крупный язь', 'uncommon', ('deep',), 0.91, 4.31, 163, 288, 131, ('Живая наживка',)),
    FishSpecies('Крупная краснопёрка', 'uncommon', ('deep', 'anomaly'), 1.05, 5.0, 175, 315, 140, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Крупная густера', 'uncommon', ('shore', 'deep'), 1.19, 5.69, 187, 252, 149, ('Аномальная наживка',)),
    FishSpecies('Крупный налим', 'uncommon', ('deep',), 1.33, 6.38, 199, 279, 158, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Крупный судак', 'uncommon', ('deep', 'anomaly'), 1.47, 2.67, 211, 306, 167, ('Хлебный мякиш',)),
    FishSpecies('Крупный сомик', 'uncommon', ('shore', 'deep'), 1.61, 3.36, 223, 333, 176, ('Черви',)),
    FishSpecies('Крупная щука', 'uncommon', ('deep',), 0.35, 2.65, 115, 240, 95, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Крупная форель', 'uncommon', ('deep', 'anomaly'), 0.49, 3.34, 127, 267, 104, ('Пахучая прикормка',)),
    FishSpecies('Крупный угорь', 'uncommon', ('shore', 'deep'), 0.63, 4.03, 139, 204, 113, ('Живая наживка',)),
    FishSpecies('Крупный бычок', 'uncommon', ('deep',), 0.77, 4.72, 151, 231, 122, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Крупный подлещик', 'uncommon', ('deep', 'anomaly'), 0.91, 5.41, 163, 258, 131, ('Аномальная наживка',)),
    FishSpecies('Крупный синец', 'uncommon', ('shore', 'deep'), 1.05, 6.1, 175, 285, 140, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Крупная чехонь', 'uncommon', ('deep',), 1.19, 2.39, 187, 312, 149, ('Хлебный мякиш',)),
    FishSpecies('Крупный вьюн', 'uncommon', ('deep', 'anomaly'), 1.33, 3.08, 199, 339, 158, ('Черви',)),
    FishSpecies('Крупная щиповка', 'uncommon', ('shore', 'deep'), 1.47, 3.77, 211, 276, 167, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Крупная верховка', 'uncommon', ('deep',), 1.61, 4.46, 223, 303, 176, ('Пахучая прикормка',)),
    FishSpecies('Крупный жерех', 'uncommon', ('deep', 'anomaly'), 0.35, 3.75, 115, 210, 95, ('Живая наживка',)),
    FishSpecies('Крупный ротан', 'uncommon', ('shore', 'deep'), 0.49, 4.44, 127, 237, 104, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Крупный сазан', 'uncommon', ('deep',), 0.63, 5.13, 139, 264, 113, ('Аномальная наживка',)),
    FishSpecies('Крупный омутник', 'uncommon', ('deep', 'anomaly'), 0.77, 5.82, 151, 291, 122, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Крупный камнекус', 'uncommon', ('shore', 'deep'), 0.91, 2.11, 163, 228, 131, ('Хлебный мякиш',)),
    FishSpecies('Крупный илохвост', 'uncommon', ('deep',), 1.05, 2.8, 175, 255, 140, ('Черви',)),
    FishSpecies('Крупный водомер', 'uncommon', ('deep', 'anomaly'), 1.19, 3.49, 187, 282, 149, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Крупный коряжник', 'uncommon', ('shore', 'deep'), 1.33, 4.18, 199, 309, 158, ('Пахучая прикормка',)),
    FishSpecies('Крупный мохоспин', 'uncommon', ('deep',), 1.47, 4.87, 211, 336, 167, ('Живая наживка',)),
    FishSpecies('Крупный желтоплав', 'uncommon', ('deep', 'anomaly'), 1.61, 5.56, 223, 363, 176, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Крупный синепёр', 'uncommon', ('shore', 'deep'), 0.35, 4.85, 115, 180, 95, ('Аномальная наживка',)),
    FishSpecies('Крупный сероспин', 'uncommon', ('deep',), 0.49, 5.54, 127, 207, 104, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Крупный пятноглаз', 'uncommon', ('deep', 'anomaly'), 0.63, 1.83, 139, 234, 113, ('Хлебный мякиш',)),
    FishSpecies('Крупный тихобрюх', 'uncommon', ('shore', 'deep'), 0.77, 2.52, 151, 261, 122, ('Черви',)),
    FishSpecies('Глубинная плотва', 'uncommon', ('deep',), 0.91, 3.21, 163, 288, 131, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Глубинный окунь', 'uncommon', ('deep', 'anomaly'), 1.05, 3.9, 175, 315, 140, ('Пахучая прикормка',)),
    FishSpecies('Глубинный карась', 'uncommon', ('shore', 'deep'), 1.19, 4.59, 187, 252, 149, ('Живая наживка',)),
    FishSpecies('Глубинная уклейка', 'uncommon', ('deep',), 1.33, 5.28, 199, 279, 158, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Глубинный ёрш', 'uncommon', ('deep', 'anomaly'), 1.47, 5.97, 211, 306, 167, ('Аномальная наживка',)),
    FishSpecies('Глубинный пескарь', 'uncommon', ('shore', 'deep'), 1.61, 6.66, 223, 333, 176, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Глубинный лещ', 'uncommon', ('deep',), 0.35, 1.55, 115, 240, 95, ('Хлебный мякиш',)),
    FishSpecies('Глубинный карп', 'uncommon', ('deep', 'anomaly'), 0.49, 2.24, 127, 267, 104, ('Черви',)),
    FishSpecies('Глубинный линь', 'uncommon', ('shore', 'deep'), 0.63, 2.93, 139, 204, 113, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Глубинный голавль', 'uncommon', ('deep',), 0.77, 3.62, 151, 231, 122, ('Пахучая прикормка',)),
    FishSpecies('Глубинный язь', 'uncommon', ('deep', 'anomaly'), 0.91, 4.31, 163, 258, 131, ('Живая наживка',)),
    FishSpecies('Глубинная краснопёрка', 'uncommon', ('shore', 'deep'), 1.05, 5.0, 175, 285, 140, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Глубинная густера', 'uncommon', ('deep',), 1.19, 5.69, 187, 312, 149, ('Аномальная наживка',)),
    FishSpecies('Глубинный налим', 'uncommon', ('deep', 'anomaly'), 1.33, 6.38, 199, 339, 158, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Глубинный озёрный судак', 'uncommon', ('shore', 'deep'), 1.47, 2.67, 211, 276, 167, ('Хлебный мякиш',)),
    FishSpecies('Глубинный сомик', 'uncommon', ('deep',), 1.61, 3.36, 223, 303, 176, ('Черви',)),
    FishSpecies('Глубинная щука', 'uncommon', ('deep', 'anomaly'), 0.35, 2.65, 115, 210, 95, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Глубинная форель', 'uncommon', ('shore', 'deep'), 0.49, 3.34, 127, 237, 104, ('Пахучая прикормка',)),
    FishSpecies('Глубинный угорь', 'uncommon', ('deep',), 0.63, 4.03, 139, 264, 113, ('Живая наживка',)),
    FishSpecies('Глубинный бычок', 'uncommon', ('deep', 'anomaly'), 0.77, 4.72, 151, 291, 122, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Глубинный подлещик', 'uncommon', ('shore', 'deep'), 0.91, 5.41, 163, 228, 131, ('Аномальная наживка',)),
    FishSpecies('Глубинный синец', 'uncommon', ('deep',), 1.05, 6.1, 175, 255, 140, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Глубинная чехонь', 'uncommon', ('deep', 'anomaly'), 1.19, 2.39, 187, 282, 149, ('Хлебный мякиш',)),
    FishSpecies('Глубинный вьюн', 'uncommon', ('shore', 'deep'), 1.33, 3.08, 199, 309, 158, ('Черви',)),
    FishSpecies('Глубинная щиповка', 'uncommon', ('deep',), 1.47, 3.77, 211, 336, 167, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Глубинная верховка', 'uncommon', ('deep', 'anomaly'), 1.61, 4.46, 223, 363, 176, ('Пахучая прикормка',)),
    FishSpecies('Глубинный жерех', 'uncommon', ('shore', 'deep'), 0.35, 3.75, 115, 180, 95, ('Живая наживка',)),
    FishSpecies('Глубинный ротан', 'uncommon', ('deep',), 0.49, 4.44, 127, 207, 104, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Глубинный сазан', 'uncommon', ('deep', 'anomaly'), 0.63, 5.13, 139, 234, 113, ('Аномальная наживка',)),
    FishSpecies('Аномальная плотва', 'rare', ('deep',), 2.59, 7.99, 312, 547, 219, ('Пахучая прикормка',)),
    FishSpecies('Аномальный окунь', 'rare', ('deep', 'anomaly'), 0.25, 6.45, 336, 606, 232, ('Живая наживка',)),
    FishSpecies('Аномальный карась', 'rare', ('anomaly',), 0.43, 7.43, 360, 665, 245, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Аномальная уклейка', 'rare', ('deep',), 0.61, 8.41, 384, 724, 258, ('Аномальная наживка',)),
    FishSpecies('Аномальный ёрш', 'rare', ('deep', 'anomaly'), 0.79, 9.39, 408, 783, 271, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Аномальный пескарь', 'rare', ('anomaly',), 0.97, 2.37, 432, 562, 284, ('Хлебный мякиш',)),
    FishSpecies('Аномальный лещ', 'rare', ('deep',), 1.15, 3.35, 456, 621, 297, ('Черви',)),
    FishSpecies('Аномальный карп', 'rare', ('deep', 'anomaly'), 1.33, 4.33, 480, 680, 310, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Аномальный линь', 'rare', ('anomaly',), 1.51, 5.31, 504, 739, 323, ('Пахучая прикормка',)),
    FishSpecies('Аномальный голавль', 'rare', ('deep',), 1.69, 6.29, 240, 510, 180, ('Живая наживка',)),
    FishSpecies('Аномальный язь', 'rare', ('deep', 'anomaly'), 1.87, 7.27, 264, 569, 193, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Аномальная краснопёрка', 'rare', ('anomaly',), 2.05, 8.25, 288, 628, 206, ('Аномальная наживка',)),
    FishSpecies('Аномальная густера', 'rare', ('deep',), 2.23, 9.23, 312, 687, 219, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Аномальный налим', 'rare', ('deep', 'anomaly'), 2.41, 10.21, 336, 466, 232, ('Хлебный мякиш',)),
    FishSpecies('Аномальный судак', 'rare', ('anomaly',), 2.59, 11.19, 360, 525, 245, ('Черви',)),
    FishSpecies('Аномальный сомик', 'rare', ('deep',), 0.25, 1.65, 384, 584, 258, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Аномальная щука', 'rare', ('deep', 'anomaly'), 0.43, 2.63, 408, 643, 271, ('Пахучая прикормка',)),
    FishSpecies('Аномальная форель', 'rare', ('anomaly',), 0.61, 3.61, 432, 702, 284, ('Живая наживка',)),
    FishSpecies('Аномальный угорь', 'rare', ('deep',), 0.79, 4.59, 456, 761, 297, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Аномальный бычок', 'rare', ('deep', 'anomaly'), 0.97, 5.57, 480, 820, 310, ('Аномальная наживка',)),
    FishSpecies('Аномальный подлещик', 'rare', ('anomaly',), 1.15, 6.55, 504, 879, 323, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Аномальный синец', 'rare', ('deep',), 1.33, 7.53, 240, 370, 180, ('Хлебный мякиш',)),
    FishSpecies('Аномальная чехонь', 'rare', ('deep', 'anomaly'), 1.51, 8.51, 264, 429, 193, ('Черви',)),
    FishSpecies('Аномальный вьюн', 'rare', ('anomaly',), 1.69, 9.49, 288, 488, 206, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Аномальная щиповка', 'rare', ('deep',), 1.87, 10.47, 312, 547, 219, ('Пахучая прикормка',)),
    FishSpecies('Аномальная верховка', 'rare', ('deep', 'anomaly'), 2.05, 3.45, 336, 606, 232, ('Живая наживка',)),
    FishSpecies('Аномальный жерех', 'rare', ('anomaly',), 2.23, 4.43, 360, 665, 245, ('Живая наживка', 'Пахучая прикормка')),
    FishSpecies('Аномальный ротан', 'rare', ('deep',), 2.41, 5.41, 384, 724, 258, ('Аномальная наживка',)),
    FishSpecies('Аномальный сазан', 'rare', ('deep', 'anomaly'), 2.59, 6.39, 408, 783, 271, ('Аномальная наживка', 'Живая наживка')),
    FishSpecies('Аномальный омутник', 'rare', ('anomaly',), 0.25, 4.85, 432, 562, 284, ('Хлебный мякиш',)),
    FishSpecies('Аномальный камнекус', 'rare', ('deep',), 0.43, 5.83, 456, 621, 297, ('Черви',)),
    FishSpecies('Аномальный илохвост', 'rare', ('deep', 'anomaly'), 0.61, 6.81, 480, 680, 310, ('Черви', 'Хлебный мякиш')),
    FishSpecies('Аномальный водомер', 'rare', ('anomaly',), 0.79, 7.79, 504, 739, 323, ('Пахучая прикормка',)),
)

_MASC_FISH_NOUNS = {
    "окунь", "карась", "ёрш", "пескарь", "лещ", "карп", "линь", "голавль", "язь",
    "налим", "судак", "сомик", "угорь", "бычок", "подлещик", "синец", "вьюн",
    "жерех", "ротан", "сазан", "омутник", "камнекус", "илохвост", "водомер",
    "коряжник", "мохоспин", "желтоплав", "синепёр", "сероспин", "пятноглаз",
    "тихобрюх",
}

_MASC_ADJECTIVES = {
    "Малая": "Малый",
    "Береговая": "Береговой",
    "Светлая": "Светлый",
    "Крупная": "Крупный",
    "Глубинная": "Глубинный",
    "Аномальная": "Аномальный",
}


def _polish_fish_species_names(species: tuple[FishSpecies, ...]) -> tuple[FishSpecies, ...]:
    polished: list[FishSpecies] = []
    seen: set[str] = set()
    for fish in species:
        parts = fish.name.split(" ", 1)
        if len(parts) != 2:
            polished.append(fish)
            seen.add(fish.name)
            continue
        adjective, noun = parts
        if noun.lower() not in _MASC_FISH_NOUNS or adjective not in _MASC_ADJECTIVES:
            polished.append(fish)
            seen.add(fish.name)
            continue
        new_name = f"{_MASC_ADJECTIVES[adjective]} {noun}"
        if new_name in seen:
            new_name = f"{_MASC_ADJECTIVES[adjective]} озёрный {noun}"
        polished.append(FishSpecies(
            new_name,
            fish.tier,
            fish.spots,
            fish.weight_min,
            fish.weight_max,
            fish.price_per_kg_min,
            fish.price_per_kg_max,
            fish.xp,
            fish.bait_bonus,
        ))
        seen.add(new_name)
    return tuple(polished)


FISH_SPECIES = _polish_fish_species_names(FISH_SPECIES)

BONUS_DROPS = [
    {
        "name": "Аномальная чешуя",
        "qty": 1,
        "chance": 2,
        "spots": {"anomaly"},
        "min_tier": "common",
    },
    {
        "name": "Затонувший контейнер",
        "qty": 1,
        "chance": 1,
        "spots": {"deep", "anomaly"},
        "min_tier": "uncommon",
    },
]

TIER_ORDER = {"junk": 0, "common": 1, "uncommon": 2, "rare": 3}

COOKING_RECIPES = {
    "уха": {
        "label": "Уха у Лучика",
        "result": ("Уха у Лучика", 1),
        "ingredients_any": {
            "fish": {
                "items": ("Серебристая плотва", "Пятнистый окунь", "Старый карась"),
                "qty": 2,
                "label": "любая обычная рыба x2",
            },
        },
        "ingredients": [("Чистая вода", 1)],
        "commands": {"приготовить уху", "уха", "сварить уху"},
    },
}

LUCHIK_ORDERS = {
    "common_fish": {
        "label": "Уха на вечер",
        "description": "принести обычную рыбу для кухни турбазы",
        "items": ("Серебристая плотва", "Пятнистый окунь", "Старый карась"),
        "qty": 3,
        "reward_money": 340,
        "reward_items": [("Черви", 2)],
        "flag": "luchik_order_common_fish_done",
        "commands": ("заказ рыба", "заказ уха", "заказ common_fish"),
    },
    "anomaly_scale": {
        "label": "Странная чешуя",
        "description": "принести редкую чешую из аномальной заводи",
        "items": ("Аномальная чешуя",),
        "qty": 1,
        "reward_money": 700,
        "reward_items": [("Черви", 3)],
        "flag": "luchik_order_anomaly_scale_done",
        "commands": ("заказ чешуя", "заказ anomaly_scale"),
    },
}


SPOT_ALIASES = {
    "береговая снасть": "shore",
    "берег": "shore",
    "тихий берег": "shore",
    "глубокий заброс": "deep",
    "заброс": "deep",
    "глубина": "deep",
    "аномальная заводь": "anomaly",
    "заводь": "anomaly",
    "аномалия": "anomaly",
}
