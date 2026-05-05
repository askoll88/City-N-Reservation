"""Banner definitions and rates for Resonance Zone."""

from __future__ import annotations

from dataclasses import dataclass


SINGLE_PULL_COST = 160
TEN_PULL_COST = 1600
BANNER_DURATION_DAYS = 20

GACHA_ENABLED_SETTING = "resonance_zone_enabled"
SIGNAL_SHARDS_FLAG = "resonance_signal_shards"
BANNER_CYCLE_START_SETTING = "resonance_banner_cycle_start_ts"

SSR_BASE_RATE = 1.6
SR_BASE_RATE = 12.0
SSR_HARD_PITY = 80
SSR_SOFT_PITY_START = 65
SSR_SOFT_PITY_STEP = 6.0
SR_HARD_PITY = 10


@dataclass(frozen=True)
class RewardEntry:
    kind: str
    name: str
    min_qty: int = 1
    max_qty: int = 1


@dataclass(frozen=True)
class Banner:
    id: str
    name: str
    featured_ssr: tuple[str, ...]
    off_ssr: tuple[str, ...]
    sr_pool: tuple[RewardEntry, ...]
    r_pool: tuple[RewardEntry, ...]


WEAPON_BANNER = Banner(
    id="weapon",
    name="Оружейный резонанс",
    featured_ssr=("АК-74 «Резонанс»",),
    off_ssr=("Винторез «Тихий Сигнал»", "Нож «Осколок Разлома»"),
    sr_pool=(
        RewardEntry("item", "ПМ «Сбой»"),
        RewardEntry("item", "ИЖ-27 «Глухой Отклик»"),
        RewardEntry("item", "Модуль резонанса оружия"),
    ),
    r_pool=(
        RewardEntry("item", "Бинт", 1, 2),
        RewardEntry("item", "Аптечка", 1, 1),
        RewardEntry("item", "Сломанный патрон", 2, 5),
        RewardEntry("item", "Ржавый болт", 1, 3),
        RewardEntry("item", "Пустая гильза", 2, 5),
    ),
)

OUTFIT_BANNER = Banner(
    id="outfit",
    name="Резонанс снаряжения",
    featured_ssr=("Плащ «Проводник Сигнала»",),
    off_ssr=(
        "Маска «Проводник Сигнала»",
        "Перчатки «Проводник Сигнала»",
        "Ботинки «Проводник Сигнала»",
    ),
    sr_pool=(
        RewardEntry("item", "Куртка «Глухой эфир»"),
        RewardEntry("item", "Маска «Пыль эфира»"),
        RewardEntry("item", "Перчатки «Сухой контакт»"),
        RewardEntry("item", "Ботинки «Тихий шаг»"),
        RewardEntry("item", "Ткань с резонансной пропиткой"),
    ),
    r_pool=(
        RewardEntry("item", "Бинт", 1, 2),
        RewardEntry("item", "Аптечка", 1, 1),
        RewardEntry("item", "Грязная тряпка", 2, 5),
        RewardEntry("item", "Обрывок проволоки", 1, 3),
        RewardEntry("item", "Ржавый болт", 1, 3),
    ),
)

BANNERS = {
    WEAPON_BANNER.id: WEAPON_BANNER,
    OUTFIT_BANNER.id: OUTFIT_BANNER,
}


def get_banner(banner_id: str) -> Banner | None:
    return BANNERS.get(str(banner_id or "").strip().lower())
