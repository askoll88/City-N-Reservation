"""
Location access checks.

The access layer is separate from navigation handlers so every future entry
point (text command, map screen, callback, event redirect) can use one contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from infra import database
from game.map_schema import get_map_location


@dataclass
class AccessResult:
    allowed: bool
    location_id: str
    location_name: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    required_level: int | None = None
    required_rank_tier: int | None = None

    @property
    def blocked(self) -> bool:
        return not self.allowed

    def format_message(self) -> str:
        if self.allowed:
            if not self.warnings:
                return ""
            return "⚠️ Маршрут открыт, но Зона предупреждает:\n" + "\n".join(f"• {line}" for line in self.warnings)

        lines = [
            "⛔ На этот маршрут тебя пока не выпускают.",
            "",
            f"Локация: {self.location_name}",
            "",
            "Что нужно закрыть перед выходом:",
        ]
        lines.extend(f"• {reason}" for reason in self.reasons)
        if self.warnings:
            lines.append("")
            lines.append("Что ещё стоит учесть:")
            lines.extend(f"• {warning}" for warning in self.warnings)
        return "\n".join(lines)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_player_level(player) -> int:
    return max(1, _safe_int(getattr(player, "level", 1), 1))


def _get_player_rank_tier(player) -> int:
    getter = getattr(player, "_get_rank_tier", None)
    if callable(getter):
        try:
            return max(1, _safe_int(getter(), 1))
        except Exception:
            pass
    return max(1, _safe_int(getattr(player, "rank_tier", 1), 1))


def get_required_rank_tier_for_level(level: int, player=None) -> int:
    """
    Infer the minimum rank tier that owns a level.

    This protects high-tier zones even when designers set only level_min:
    a low-rank player cannot enter, die, and keep high-tier loot.
    """
    target_level = max(1, _safe_int(level, 1))
    tiers = getattr(player, "RANK_TIERS", None)
    if not tiers:
        try:
            from models.player import Player
            tiers = Player.RANK_TIERS
        except Exception:
            tiers = []
    if not tiers:
        return 1

    required_tier = 1
    for idx, tier in enumerate(tiers, start=1):
        min_level = _safe_int(tier.get("min_level", 1), 1)
        max_level = _safe_int(tier.get("max_level", min_level), min_level)
        if min_level <= target_level <= max_level:
            return idx
        if target_level >= min_level:
            required_tier = idx
    return max(1, required_tier)


def _iter_inventory_item_names(player) -> set[str]:
    names: set[str] = set()
    inventory = getattr(player, "inventory", None)
    if not inventory:
        return names
    for section in ("weapons", "armor", "backpacks", "artifacts", "shells_bags", "other"):
        for item in getattr(inventory, section, []) or []:
            qty = _safe_int(item.get("quantity", 1), 1) if isinstance(item, dict) else 1
            name = item.get("name") if isinstance(item, dict) else None
            if name and qty > 0:
                names.add(str(name).lower())
    return names


def _has_inventory_item(player, item_name: str) -> bool:
    if not item_name:
        return False
    return item_name.lower() in _iter_inventory_item_names(player)


def _get_equipped_names(player) -> set[str]:
    fields = (
        "equipped_weapon",
        "equipped_armor",
        "equipped_armor_head",
        "equipped_armor_body",
        "equipped_armor_legs",
        "equipped_armor_hands",
        "equipped_armor_feet",
        "equipped_backpack",
        "equipped_device",
        "equipped_shells_bag",
    )
    names = {
        str(getattr(player, field)).lower()
        for field in fields
        if getattr(player, field, None)
    }
    names.update(str(name).lower() for name in (getattr(player, "equipped_artifacts", []) or []))
    return names


def _has_equipped(player, required_name: str) -> bool:
    return bool(required_name) and required_name.lower() in _get_equipped_names(player)


def _get_flag(player, flag_name: str) -> int:
    if not flag_name:
        return 0
    local_value = getattr(player, flag_name, None)
    if local_value is not None:
        return _safe_int(local_value, 0)
    user_id = getattr(player, "user_id", None)
    if user_id is None:
        return 0
    try:
        return _safe_int(database.get_user_flag(int(user_id), flag_name, 0), 0)
    except Exception:
        return 0


def _has_flag(player, flag_name: str) -> bool:
    return _get_flag(player, flag_name) > 0


def _has_key(player, key_name: str) -> bool:
    if not key_name:
        return False
    key = str(key_name)
    return (
        _has_inventory_item(player, key)
        or _has_flag(player, key)
        or _has_flag(player, f"key:{key}")
        or _has_flag(player, f"key_{key}")
    )


def _get_reputation(player, faction: str) -> int:
    reputation = getattr(player, "reputation", None)
    if isinstance(reputation, dict):
        return _safe_int(reputation.get(faction, 0), 0)
    return max(
        _get_flag(player, f"reputation:{faction}"),
        _get_flag(player, f"reputation_{faction}"),
    )


def _missing_required_list(player, values: list[str], checker) -> list[str]:
    return [value for value in values if not checker(player, value)]


def can_enter_location(player, location_id: str) -> AccessResult:
    record = get_map_location(location_id)
    if not record:
        return AccessResult(
            allowed=False,
            location_id=location_id,
            location_name=location_id,
            reasons=["Локация не найдена в карте."],
        )

    player_level = _get_player_level(player)
    player_rank = _get_player_rank_tier(player)
    location_name = str(record.get("name") or location_id)
    reasons: list[str] = []
    warnings: list[str] = []

    required_level = max(1, _safe_int(record.get("level_min", 1), 1))
    if player_level < required_level:
        reasons.append(f"уровень {required_level}+ (сейчас {player_level})")

    required_rank = get_required_rank_tier_for_level(required_level, player=player)
    explicit_rank = _safe_int(record.get("requires", {}).get("rank_tier", 0), 0)
    if explicit_rank > 0:
        required_rank = max(required_rank, explicit_rank)
    if player_rank < required_rank:
        reasons.append(f"ранг {required_rank}+ (сейчас {player_rank})")

    level_max = _safe_int(record.get("level_max", required_level), required_level)
    if player_level > level_max:
        warnings.append(f"Рекомендуемый диапазон зоны: {required_level}-{level_max} ур.")

    requires = record.get("requires", {}) or {}

    level_req = _safe_int(requires.get("level", requires.get("level_min", 0)), 0)
    if level_req > 0 and player_level < level_req:
        reasons.append(f"уровень {level_req}+ (сейчас {player_level})")

    key = requires.get("key")
    if key and not _has_key(player, str(key)):
        reasons.append(f"ключ: {key}")
    missing_keys = _missing_required_list(player, list(requires.get("keys", []) or []), _has_key)
    if missing_keys:
        reasons.append("ключи: " + ", ".join(missing_keys))

    item = requires.get("item")
    if item and not _has_inventory_item(player, str(item)):
        reasons.append(f"предмет: {item}")
    missing_items = _missing_required_list(player, list(requires.get("items", []) or []), _has_inventory_item)
    if missing_items:
        reasons.append("предметы: " + ", ".join(missing_items))

    for flag_key in ("flag", "quest_flag"):
        flag = requires.get(flag_key)
        if flag and not _has_flag(player, str(flag)):
            reasons.append(f"флаг: {flag}")
    required_flags = list(requires.get("flags", []) or []) + list(requires.get("quest_flags", []) or [])
    missing_flags = _missing_required_list(player, required_flags, _has_flag)
    if missing_flags:
        reasons.append("флаги: " + ", ".join(missing_flags))

    equipped = list(requires.get("equipped", []) or [])
    missing_equipped = _missing_required_list(player, equipped, _has_equipped)
    if missing_equipped:
        reasons.append("экипировка: " + ", ".join(missing_equipped))

    reputation = requires.get("reputation", {}) or {}
    for faction, amount in reputation.items():
        got = _get_reputation(player, str(faction))
        need = _safe_int(amount, 0)
        if got < need:
            reasons.append(f"репутация {faction}: {need}+ (сейчас {got})")

    radiation_max = _safe_int(requires.get("radiation_max", 0), 0)
    if radiation_max > 0:
        radiation = _safe_int(getattr(player, "radiation", 0), 0)
        if radiation > radiation_max:
            reasons.append(f"радиация не выше {radiation_max} (сейчас {radiation})")

    artifact_slots = _safe_int(requires.get("artifact_slots", 0), 0)
    if artifact_slots > 0:
        got_slots = _safe_int(getattr(player, "artifact_slots", 0), 0)
        if got_slots < artifact_slots:
            reasons.append(f"слоты артефактов {artifact_slots}+ (сейчас {got_slots})")

    money = _safe_int(requires.get("money", 0), 0)
    if money > 0:
        got_money = _safe_int(getattr(player, "money", 0), 0)
        if got_money < money:
            reasons.append(f"деньги {money}+ руб. (сейчас {got_money})")

    defense_req = max(_safe_int(requires.get("defense", 0), 0), _safe_int(requires.get("total_defense", 0), 0))
    if defense_req > 0:
        defense = _safe_int(getattr(player, "total_defense", 0), 0)
        if defense < defense_req:
            reasons.append(f"защита {defense_req}+ (сейчас {defense})")

    return AccessResult(
        allowed=not reasons,
        location_id=location_id,
        location_name=location_name,
        reasons=reasons,
        warnings=warnings,
        required_level=required_level,
        required_rank_tier=required_rank,
    )
