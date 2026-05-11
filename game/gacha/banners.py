"""Banner definitions and rates for Resonance Zone."""

from __future__ import annotations

from dataclasses import dataclass


SINGLE_PULL_COST = 160
TEN_PULL_COST = 1600
BANNER_DURATION_DAYS = 20
BANNER_PHASES_PER_PATCH = 2
BANNER_PATCH_DURATION_DAYS = BANNER_DURATION_DAYS * BANNER_PHASES_PER_PATCH

GACHA_ENABLED_SETTING = "resonance_zone_enabled"
SIGNAL_SHARDS_FLAG = "resonance_signal_shards"
BANNER_CYCLE_START_SETTING = "resonance_banner_cycle_start_ts"
BANNER_ROTATION_INDEX_SETTING = "resonance_banner_rotation_index"

SSR_BASE_RATE = 1.6
SSR_CONSOLIDATED_RATE = 2.36
FEATURED_SSR_CONSOLIDATED_RATE = 1.57
SR_BASE_RATE = 12.0
SR_CONSOLIDATED_RATE = 16.0
SSR_HARD_PITY = 80
SSR_SOFT_PITY_START = 65
SSR_SOFT_PITY_STEP = 6.0
OUTFIT_SSR_HARD_PITY = 60
OUTFIT_SSR_SOFT_PITY_START = 45
OUTFIT_SSR_SOFT_PITY_STEP = 7.0
SR_HARD_PITY = 10

WEAPON_OFFRATE_SSR_POOL = (
    "АКС-74 «Серый Контур»",
    "СВД «Шум Предела»",
    "Клинок «Немой Разлом»",
)
OUTFIT_OFFRATE_SSR_POOL = (
    "Шлем «Глухой Контур»",
    "Перчатки «Эхоизоляция»",
    "Ботинки «Серый Маршрут»",
)
FEATURED_SSR_EXCLUSIVE_NAMES = frozenset({
    "АК-74 «Резонанс»",
    "Винторез «Тихий Сигнал»",
    "Нож «Осколок Разлома»",
    "Плащ «Проводник Сигнала»",
    "Маска «Проводник Сигнала»",
    "Перчатки «Проводник Сигнала»",
    "Ботинки «Проводник Сигнала»",
    "Плащ «Искатель Разлома»",
    "Маска «Искатель Разлома»",
    "Перчатки «Искатель Разлома»",
    "Ботинки «Искатель Разлома»",
})

SIGNAL_GUIDE_SET = (
    "Плащ «Проводник Сигнала»",
    "Маска «Проводник Сигнала»",
    "Перчатки «Проводник Сигнала»",
    "Ботинки «Проводник Сигнала»",
)
RUPTURE_SEEKER_SET = (
    "Плащ «Искатель Разлома»",
    "Маска «Искатель Разлома»",
    "Перчатки «Искатель Разлома»",
    "Ботинки «Искатель Разлома»",
)


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
    featured_sr: tuple[RewardEntry, ...]
    off_sr: tuple[RewardEntry, ...]
    sr_pool: tuple[RewardEntry, ...]
    r_pool: tuple[RewardEntry, ...]


WEAPON_BANNER = Banner(
    id="weapon",
    name="Оружейный резонанс",
    featured_ssr=("АК-74 «Резонанс»",),
    off_ssr=WEAPON_OFFRATE_SSR_POOL,
    featured_sr=(
        RewardEntry("item", "ПМ «Сбой»"),
        RewardEntry("item", "Модуль резонанса оружия"),
    ),
    off_sr=(
        RewardEntry("item", "ИЖ-27 «Глухой Отклик»"),
    ),
    sr_pool=(
        RewardEntry("item", "ПМ «Сбой»"),
        RewardEntry("item", "ИЖ-27 «Глухой Отклик»"),
        RewardEntry("item", "Модуль резонанса оружия"),
    ),
    r_pool=(
        RewardEntry("item", "Бинт", 1, 2),
        RewardEntry("item", "Аптечка", 1, 1),
        RewardEntry("item", "Металлолом", 2, 5),
        RewardEntry("item", "Медная проволока", 1, 3),
        RewardEntry("item", "Аномальный шлак", 1, 2),
        RewardEntry("item", "Комок ржавой стружки", 2, 6),
        RewardEntry("item", "Почерневшая батарейка", 1, 3),
        RewardEntry("item", "Пыльный предохранитель", 1, 3),
    ),
)

OUTFIT_BANNER = Banner(
    id="outfit",
    name="Резонанс снаряжения",
    featured_ssr=SIGNAL_GUIDE_SET,
    off_ssr=OUTFIT_OFFRATE_SSR_POOL,
    featured_sr=(
        RewardEntry("item", "Куртка «Глухой эфир»"),
        RewardEntry("item", "Ткань с резонансной пропиткой"),
    ),
    off_sr=(
        RewardEntry("item", "Маска «Пыль эфира»"),
        RewardEntry("item", "Перчатки «Сухой контакт»"),
        RewardEntry("item", "Ботинки «Тихий шаг»"),
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
        RewardEntry("item", "Ветошь", 2, 5),
        RewardEntry("item", "Стеклянная тара", 1, 3),
        RewardEntry("item", "Старые документы", 1, 3),
        RewardEntry("item", "Провонявший бинт", 2, 6),
        RewardEntry("item", "Пустой фильтр", 1, 4),
        RewardEntry("item", "Слипшийся блокнот", 1, 3),
    ),
)

BANNERS = {
    WEAPON_BANNER.id: WEAPON_BANNER,
    OUTFIT_BANNER.id: OUTFIT_BANNER,
}

BANNER_PHASES: tuple[dict[str, Banner], ...] = (
    {
        "weapon": WEAPON_BANNER,
        "outfit": OUTFIT_BANNER,
    },
    {
        "weapon": Banner(
            id="weapon",
            name="Оружейный резонанс: тихий сигнал",
            featured_ssr=("Винторез «Тихий Сигнал»",),
            off_ssr=WEAPON_OFFRATE_SSR_POOL,
            featured_sr=(
                RewardEntry("item", "ИЖ-27 «Глухой Отклик»"),
                RewardEntry("item", "Модуль резонанса оружия"),
            ),
            off_sr=(
                RewardEntry("item", "ПМ «Сбой»"),
            ),
            sr_pool=WEAPON_BANNER.sr_pool,
            r_pool=WEAPON_BANNER.r_pool,
        ),
        "outfit": Banner(
            id="outfit",
            name="Резонанс снаряжения: искатель разлома",
            featured_ssr=RUPTURE_SEEKER_SET,
            off_ssr=OUTFIT_OFFRATE_SSR_POOL,
            featured_sr=(
                RewardEntry("item", "Маска «Пыль эфира»"),
                RewardEntry("item", "Ткань с резонансной пропиткой"),
            ),
            off_sr=(
                RewardEntry("item", "Куртка «Глухой эфир»"),
                RewardEntry("item", "Перчатки «Сухой контакт»"),
                RewardEntry("item", "Ботинки «Тихий шаг»"),
            ),
            sr_pool=OUTFIT_BANNER.sr_pool,
            r_pool=OUTFIT_BANNER.r_pool,
        ),
    },
)


def get_banner(banner_id: str) -> Banner | None:
    return BANNERS.get(str(banner_id or "").strip().lower())


def build_phase_banners(phase_index: int) -> dict[str, Banner]:
    safe_index = max(0, int(phase_index or 0)) % len(BANNER_PHASES)
    return dict(BANNER_PHASES[safe_index])


def default_offrate_ssr_pool(banner_id: str) -> tuple[str, ...]:
    return OUTFIT_OFFRATE_SSR_POOL if str(banner_id or "").strip().lower() == "outfit" else WEAPON_OFFRATE_SSR_POOL


def sanitize_offrate_ssr(banner_id: str, featured_ssr: tuple[str, ...], off_ssr: tuple[str, ...]) -> tuple[str, ...]:
    blocked = set(FEATURED_SSR_EXCLUSIVE_NAMES)
    blocked.update(str(item) for item in featured_ssr or ())
    cleaned = tuple(str(item) for item in off_ssr or () if item and str(item) not in blocked)
    return cleaned or default_offrate_ssr_pool(banner_id)


def get_ssr_hard_pity(banner_id: str) -> int:
    return OUTFIT_SSR_HARD_PITY if str(banner_id or "").strip().lower() == "outfit" else SSR_HARD_PITY


def get_ssr_soft_pity_start(banner_id: str) -> int:
    return OUTFIT_SSR_SOFT_PITY_START if str(banner_id or "").strip().lower() == "outfit" else SSR_SOFT_PITY_START


def get_ssr_soft_pity_step(banner_id: str) -> float:
    return OUTFIT_SSR_SOFT_PITY_STEP if str(banner_id or "").strip().lower() == "outfit" else SSR_SOFT_PITY_STEP


def reward_entry_to_dict(entry: RewardEntry) -> dict:
    return {
        "kind": entry.kind,
        "name": entry.name,
        "min_qty": int(entry.min_qty),
        "max_qty": int(entry.max_qty),
    }


def reward_entry_from_dict(data: dict) -> RewardEntry:
    return RewardEntry(
        kind=str(data.get("kind") or "item"),
        name=str(data.get("name") or ""),
        min_qty=max(1, int(data.get("min_qty", 1) or 1)),
        max_qty=max(1, int(data.get("max_qty", data.get("min_qty", 1)) or 1)),
    )


def banner_to_dict(banner: Banner) -> dict:
    return {
        "id": banner.id,
        "name": banner.name,
        "featured_ssr": list(banner.featured_ssr),
        "off_ssr": list(sanitize_offrate_ssr(banner.id, banner.featured_ssr, banner.off_ssr)),
        "featured_sr": [reward_entry_to_dict(entry) for entry in banner.featured_sr],
        "off_sr": [reward_entry_to_dict(entry) for entry in banner.off_sr],
        "sr_pool": [reward_entry_to_dict(entry) for entry in banner.sr_pool],
        "r_pool": [reward_entry_to_dict(entry) for entry in banner.r_pool],
    }


def banner_from_dict(data: dict) -> Banner:
    banner_id = str(data.get("id") or "")
    banner_name = str(data.get("name") or "")
    featured_ssr = tuple(str(item) for item in data.get("featured_ssr", []) if item)
    if banner_id == "outfit":
        lower_name = banner_name.lower()
        if "маска проводника" in lower_name or set(featured_ssr).issubset(set(RUPTURE_SEEKER_SET)):
            banner_name = "Резонанс снаряжения: искатель разлома"
            featured_ssr = RUPTURE_SEEKER_SET
        elif set(featured_ssr).issubset(set(SIGNAL_GUIDE_SET)):
            featured_ssr = SIGNAL_GUIDE_SET
    sr_pool = tuple(reward_entry_from_dict(entry) for entry in data.get("sr_pool", []) if isinstance(entry, dict))
    featured_sr = tuple(reward_entry_from_dict(entry) for entry in data.get("featured_sr", []) if isinstance(entry, dict))
    off_sr = tuple(reward_entry_from_dict(entry) for entry in data.get("off_sr", []) if isinstance(entry, dict))
    if sr_pool and not featured_sr and not off_sr:
        split_at = max(1, min(2, len(sr_pool)))
        featured_sr = sr_pool[:split_at]
        off_sr = sr_pool[split_at:]
    return Banner(
        id=banner_id,
        name=banner_name,
        featured_ssr=featured_ssr,
        off_ssr=sanitize_offrate_ssr(
            banner_id,
            featured_ssr,
            tuple(str(item) for item in data.get("off_ssr", []) if item),
        ),
        featured_sr=featured_sr,
        off_sr=off_sr,
        sr_pool=sr_pool,
        r_pool=tuple(reward_entry_from_dict(entry) for entry in data.get("r_pool", []) if isinstance(entry, dict)),
    )
