"""
Structured map metadata and validation.

This module intentionally sits above the legacy `models.locations.LOCATIONS`
dict. Runtime navigation can keep using the old structure, while new map
features can rely on normalized metadata.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from game.constants import (
    ITEM_CATEGORY_DROP_CHANCES_BY_LOCATION,
    LOCATION_DROP_BALANCE_RULES,
    LOCATION_LEVEL_THRESHOLDS,
    RESEARCH_LOCATIONS,
    SAFE_LOCATIONS,
)
from game.location_mechanics import LOCATION_MODIFIERS
from models.enemies import ENEMIES
from models.locations import LOCATIONS


LOCATION_TYPES = {
    "hub",
    "route",
    "field",
    "dungeon",
    "resource_job",
    "raid",
    "boss_arena",
    "safehouse",
}

DANGER_LEVELS = {"safe", "low", "medium", "high", "extreme"}

REQUIREMENT_KEYS = {
    "level",
    "level_min",
    "rank_tier",
    "key",
    "keys",
    "item",
    "items",
    "flag",
    "flags",
    "quest_flag",
    "quest_flags",
    "reputation",
    "equipped",
    "radiation_max",
    "artifact_slots",
    "money",
    "defense",
    "total_defense",
}

RESEARCH_ACTIVITIES = {"research"}


# Metadata only. Name, exits and legacy actions are read from LOCATIONS to keep
# the current bot navigation contract in one place.
LOCATION_METADATA: dict[str, dict[str, Any]] = {
    "город": {
        "region": "city",
        "type": "hub",
        "level_min": 1,
        "level_max": 1,
        "danger": "safe",
        "tags": ["safe", "service", "start", "social"],
        "requires": {},
        "activities": ["heal_access", "trade_access", "storage_access", "travel"],
        "loot_profile": None,
    },
    "кпп": {
        "region": "checkpoint",
        "type": "hub",
        "level_min": 1,
        "level_max": 5,
        "danger": "safe",
        "tags": ["safe", "gate", "npc", "travel"],
        "requires": {},
        "activities": ["talk", "trade", "travel"],
        "loot_profile": None,
    },
    "больница": {
        "region": "city",
        "type": "safehouse",
        "level_min": 1,
        "level_max": 1,
        "danger": "safe",
        "tags": ["safe", "healing", "service"],
        "requires": {},
        "activities": ["heal", "rest"],
        "loot_profile": None,
    },
    "черный рынок": {
        "region": "city",
        "type": "hub",
        "level_min": 1,
        "level_max": 1,
        "danger": "safe",
        "tags": ["safe", "trade", "black_market"],
        "requires": {},
        "activities": ["trade", "sell", "buy"],
        "loot_profile": None,
    },
    "убежище": {
        "region": "city",
        "type": "safehouse",
        "level_min": 1,
        "level_max": 1,
        "danger": "safe",
        "tags": ["safe", "rest", "storage", "base"],
        "requires": {},
        "activities": ["rest", "storage", "passive_regen"],
        "loot_profile": None,
    },
    "инвентарь": {
        "region": "system",
        "type": "hub",
        "level_min": 1,
        "level_max": 1,
        "danger": "safe",
        "tags": ["ui", "inventory"],
        "requires": {},
        "activities": ["inventory"],
        "loot_profile": None,
    },
    "дорога_военная_часть": {
        "region": "military",
        "type": "route",
        "level_min": 1,
        "level_max": 5,
        "danger": "medium",
        "tags": ["research", "military", "route", "ambush", "weapons", "armor"],
        "requires": {},
        "activities": ["research", "combat", "stash"],
        "loot_profile": "military",
    },
    "военная_часть": {
        "region": "military",
        "type": "dungeon",
        "level_min": 5,
        "level_max": 10,
        "danger": "high",
        "tags": ["research", "military", "interior", "patrol", "ambush", "weapons", "armor"],
        "requires": {},
        "activities": ["research", "combat", "stash", "raid"],
        "loot_profile": "military",
    },
    "дорога_нии": {
        "region": "science",
        "type": "route",
        "level_min": 1,
        "level_max": 5,
        "danger": "medium",
        "tags": ["research", "science", "route", "anomaly", "radiation", "artifacts"],
        "requires": {},
        "activities": ["research", "combat", "anomaly"],
        "loot_profile": "scientific",
    },
    "главный_корпус_нии": {
        "region": "science",
        "type": "dungeon",
        "level_min": 5,
        "level_max": 10,
        "danger": "high",
        "tags": ["research", "science", "interior", "anomaly", "radiation", "data", "artifacts"],
        "requires": {},
        "activities": ["research", "combat", "anomaly", "intel"],
        "loot_profile": "scientific",
    },
    "дорога_зараженный_лес": {
        "region": "forest",
        "type": "route",
        "level_min": 3,
        "level_max": 7,
        "danger": "high",
        "tags": ["research", "forest", "route", "mutants", "organic", "radiation"],
        "requires": {},
        "activities": ["research", "combat", "hunt"],
        "loot_profile": "organic",
    },
    "зараженный_лес": {
        "region": "forest",
        "type": "field",
        "level_min": 5,
        "level_max": 10,
        "danger": "high",
        "tags": ["research", "forest", "interior", "mutants", "organic", "hunt", "radiation"],
        "requires": {},
        "activities": ["research", "combat", "hunt", "trophy"],
        "loot_profile": "organic",
    },
}


def build_map_locations() -> dict[str, dict[str, Any]]:
    """Build normalized map records from legacy locations plus metadata."""
    records: dict[str, dict[str, Any]] = {}
    for location_id, location in LOCATIONS.items():
        meta = deepcopy(LOCATION_METADATA.get(location_id, {}))
        record = {
            "id": location_id,
            "name": location.get("name", location_id),
            "region": meta.get("region", "unknown"),
            "type": meta.get("type", "hub"),
            "level_min": int(meta.get("level_min", 1) or 1),
            "level_max": int(meta.get("level_max", meta.get("level_min", 1)) or 1),
            "danger": meta.get("danger", "safe"),
            "tags": list(meta.get("tags", [])),
            "requires": dict(meta.get("requires", {})),
            "exits": dict(location.get("exits", {})),
            "activities": list(meta.get("activities", location.get("actions", []))),
            "loot_profile": meta.get("loot_profile"),
            "legacy_actions": list(location.get("actions", [])),
        }
        records[location_id] = record
    return records


MAP_LOCATIONS = build_map_locations()


def get_map_location(location_id: str) -> dict[str, Any] | None:
    """Return a normalized map record for one location."""
    return build_map_locations().get(location_id)


def get_map_locations() -> dict[str, dict[str, Any]]:
    """Return normalized map records for all legacy locations."""
    return build_map_locations()


def get_locations_by_region(region: str) -> list[dict[str, Any]]:
    """Return normalized locations for a region."""
    region_id = str(region or "").strip()
    return [
        record
        for record in build_map_locations().values()
        if record.get("region") == region_id
    ]


def get_locations_by_type(location_type: str) -> list[dict[str, Any]]:
    """Return normalized locations for one map type."""
    type_id = str(location_type or "").strip()
    return [
        record
        for record in build_map_locations().values()
        if record.get("type") == type_id
    ]


def get_research_map_locations() -> list[dict[str, Any]]:
    """Return normalized records for current research-capable locations."""
    locations = build_map_locations()
    return [locations[loc_id] for loc_id in RESEARCH_LOCATIONS if loc_id in locations]


def validate_location_requires(location_id: str, requires: dict[str, Any]) -> list[str]:
    """Validate requirement schema without evaluating it against a player."""
    errors: list[str] = []
    if not isinstance(requires, dict):
        return [f"{location_id}: requires must be dict"]

    for key, value in requires.items():
        if key not in REQUIREMENT_KEYS:
            errors.append(f"{location_id}: unknown requirement '{key}'")
            continue
        if key in {"level", "level_min", "rank_tier", "radiation_max", "artifact_slots", "money"}:
            if not isinstance(value, int) or value < 0:
                errors.append(f"{location_id}: requirement '{key}' must be non-negative int")
        elif key in {"defense", "total_defense"}:
            if not isinstance(value, int) or value < 0:
                errors.append(f"{location_id}: requirement '{key}' must be non-negative int")
        elif key in {"key", "item", "flag", "quest_flag"}:
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{location_id}: requirement '{key}' must be non-empty string")
        elif key in {"keys", "items", "flags", "quest_flags", "equipped"}:
            if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
                errors.append(f"{location_id}: requirement '{key}' must be list[str]")
        elif key == "reputation":
            if not isinstance(value, dict):
                errors.append(f"{location_id}: requirement 'reputation' must be dict")
            else:
                for faction, amount in value.items():
                    if not isinstance(faction, str) or not faction.strip():
                        errors.append(f"{location_id}: reputation faction must be non-empty string")
                    if not isinstance(amount, int):
                        errors.append(f"{location_id}: reputation amount for '{faction}' must be int")
    return errors


def validate_map_schema() -> list[str]:
    """Validate the structured map contract. Returns all errors."""
    errors: list[str] = []
    map_locations = build_map_locations()

    for location_id in LOCATIONS:
        if location_id not in LOCATION_METADATA:
            errors.append(f"{location_id}: missing LOCATION_METADATA")

    for location_id, record in map_locations.items():
        if record.get("id") != location_id:
            errors.append(f"{location_id}: id field mismatch")
        if not isinstance(record.get("name"), str) or not record["name"].strip():
            errors.append(f"{location_id}: name must be non-empty string")
        if not isinstance(record.get("region"), str) or not record["region"].strip():
            errors.append(f"{location_id}: region must be non-empty string")
        if record.get("type") not in LOCATION_TYPES:
            errors.append(f"{location_id}: unknown type '{record.get('type')}'")

        level_min = record.get("level_min")
        level_max = record.get("level_max")
        if not isinstance(level_min, int) or level_min < 1:
            errors.append(f"{location_id}: level_min must be positive int")
        if not isinstance(level_max, int) or level_max < 1:
            errors.append(f"{location_id}: level_max must be positive int")
        if isinstance(level_min, int) and isinstance(level_max, int) and level_min > level_max:
            errors.append(f"{location_id}: level_min cannot exceed level_max")

        if record.get("danger") not in DANGER_LEVELS:
            errors.append(f"{location_id}: unknown danger '{record.get('danger')}'")
        if not isinstance(record.get("tags"), list) or not all(isinstance(t, str) for t in record["tags"]):
            errors.append(f"{location_id}: tags must be list[str]")
        if not isinstance(record.get("activities"), list) or not all(isinstance(a, str) for a in record["activities"]):
            errors.append(f"{location_id}: activities must be list[str]")

        errors.extend(validate_location_requires(location_id, record.get("requires", {})))

        exits = record.get("exits")
        if not isinstance(exits, dict):
            errors.append(f"{location_id}: exits must be dict")
        else:
            for alias, target_id in exits.items():
                if not isinstance(alias, str) or not alias.strip():
                    errors.append(f"{location_id}: exit alias must be non-empty string")
                if target_id not in LOCATIONS:
                    errors.append(f"{location_id}: exit '{alias}' points to missing '{target_id}'")

    for location_id in RESEARCH_LOCATIONS:
        record = map_locations.get(location_id)
        if not record:
            errors.append(f"{location_id}: research location missing from map")
            continue
        if "research" not in record.get("activities", []):
            errors.append(f"{location_id}: research location must have research activity")
        if location_id not in LOCATION_MODIFIERS:
            errors.append(f"{location_id}: research location missing LOCATION_MODIFIERS")
        if location_id not in ENEMIES:
            errors.append(f"{location_id}: research location missing ENEMIES")
        if location_id not in ITEM_CATEGORY_DROP_CHANCES_BY_LOCATION:
            errors.append(f"{location_id}: research location missing drop chances")
        if location_id not in LOCATION_LEVEL_THRESHOLDS:
            errors.append(f"{location_id}: research location missing level thresholds")
        if location_id not in LOCATION_DROP_BALANCE_RULES:
            errors.append(f"{location_id}: research location missing drop balance rules")

    for location_id in SAFE_LOCATIONS:
        record = map_locations.get(location_id)
        if not record:
            errors.append(f"{location_id}: safe location missing from map")
            continue
        if record.get("danger") != "safe":
            errors.append(f"{location_id}: safe location must have danger=safe")
        if record.get("type") not in {"hub", "safehouse"}:
            errors.append(f"{location_id}: safe location must be hub or safehouse")

    return errors


def assert_valid_map_schema():
    """Raise AssertionError with a readable report if map schema is invalid."""
    errors = validate_map_schema()
    if errors:
        raise AssertionError("Invalid map schema:\n" + "\n".join(f"- {err}" for err in errors))
