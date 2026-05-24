"""Runtime fishing mechanics.

Public functions are re-exported from game.fishing so existing imports keep
working while content lives in game.fishing.content.
"""
from __future__ import annotations

import random
import time

from infra import database
from models.player import invalidate_player_cache

from .content import (
    BAITS,
    BONUS_DROPS,
    COOKING_RECIPES,
    FALLBACK_GEAR,
    FISH_LOCKER_CAPACITY,
    FISHING_DURATION_SECONDS,
    FISHING_STATE_KEY,
    FISH_SPECIES,
    GEAR,
    JUNK_CATCHES,
    LAKE_LOCATION,
    LUCHIK_ORDERS,
    LUCHIK_ROD_UPGRADES,
    LUCHIK_SHOP_ITEMS,
    SPOT_ALIASES,
    SPOTS,
    TIER_ORDER,
    FishingBait,
    FishingGear,
    FishingSpot,
    FishSpecies,
)

FISH_SPECIES_NAMES = frozenset(row.name for row in FISH_SPECIES)


def _now() -> int:
    return int(time.time())


def _get_state(vk_id: int) -> dict | None:
    state = database.get_runtime_state(vk_id, FISHING_STATE_KEY)
    return state if isinstance(state, dict) and state else None


def _set_state(vk_id: int, state: dict):
    database.set_runtime_state(vk_id, FISHING_STATE_KEY, state)


def _clear_state(vk_id: int):
    database.clear_runtime_state(vk_id, FISHING_STATE_KEY)


def _get_keepnet(vk_id: int) -> list[dict]:
    return database.get_user_fish_locker(vk_id)


def _restore_keepnet(vk_id: int, consumed: list[dict]):
    if not consumed:
        return
    database.restore_fish_locker_entries(vk_id, consumed)


def _consume_fish_from_keepnet(
    vk_id: int,
    item_names: tuple[str, ...] | list[str],
    quantity: int,
) -> tuple[bool, str, list[dict]]:
    """Consume fish instances from the tourbase fish locker."""
    result = database.consume_fish_locker_entries_transaction(vk_id, item_names, quantity)
    return bool(result.get("success")), str(result.get("used_text") or ""), list(result.get("consumed") or [])


def _fish_any_groups(recipe: dict) -> tuple[dict, list[dict]]:
    recipe_for_db = dict(recipe)
    db_any_groups: dict[str, dict] = {}
    locker_groups: list[dict] = []
    for group_id, group in (recipe.get("ingredients_any") or {}).items():
        items = tuple(group.get("items") or ())
        if items and set(items).issubset(FISH_SPECIES_NAMES):
            locker_groups.append(group)
        else:
            db_any_groups[group_id] = group
    recipe_for_db["ingredients_any"] = db_any_groups
    return recipe_for_db, locker_groups


def _stat(player, name: str) -> int:
    return max(0, int(getattr(player, name, 0) or 0))


def _inventory_quantities(vk_id: int, names: tuple[str, ...] | list[str]) -> dict[str, int]:
    getter = getattr(database, "get_inventory_item_quantities", None)
    if callable(getter):
        return getter(vk_id, tuple(names))
    return {}


def _format_item_requirements(requirements: list[tuple[str, int]] | tuple[tuple[str, int], ...]) -> str:
    return ", ".join(f"{name} x{qty}" for name, qty in requirements)


def _select_gear(vk_id: int) -> FishingGear:
    quantities = _inventory_quantities(vk_id, [gear.name for gear in GEAR])
    available = [gear for gear in GEAR if quantities.get(gear.name, 0) > 0]
    return max(available, key=lambda gear: gear.tier, default=FALLBACK_GEAR)


def _select_bait(vk_id: int) -> FishingBait | None:
    quantities = _inventory_quantities(vk_id, [bait.name for bait in BAITS])
    for bait in BAITS:
        if quantities.get(bait.name, 0) > 0:
            return bait
    return None


def _gear_bonus_for_spot(gear: FishingGear, spot: FishingSpot) -> int:
    if spot.id == "deep":
        return gear.deep_bonus
    if spot.id == "anomaly":
        return gear.anomaly_bonus
    return 0


def _pick_tier(
    player,
    spot: FishingSpot,
    seed: int,
    gear: FishingGear = FALLBACK_GEAR,
    bait: FishingBait | None = None,
) -> tuple[str, bool]:
    rng = random.Random(seed)
    perception = _stat(player, "perception")
    luck = _stat(player, "luck")
    level = _stat(player, "level")
    score = rng.randint(1, 100)
    score += min(16, perception)
    score += min(20, luck * 2)
    score += min(10, level // 4)
    score += spot.score_bonus
    score += gear.rare_bonus + gear.junk_resist + _gear_bonus_for_spot(gear, spot)
    if bait:
        score += bait.rare_bonus + bait.junk_resist

    hazard_chance = max(1, spot.risk - luck // 3 - gear.hazard_resist)
    hazard = rng.randint(1, 100) <= hazard_chance
    if hazard:
        score -= rng.randint(4, 16)

    rare_shift = spot.rare_bonus + gear.rare_bonus + (bait.rare_bonus if bait else 0)
    if score < 30:
        return "junk", hazard
    if score < 72:
        return "common", hazard
    if score < 94 - rare_shift:
        return "uncommon", hazard
    return "rare", hazard


def _roll_bonus_drops(
    spot: FishingSpot,
    tier: str,
    rng: random.Random,
    gear: FishingGear,
    bait: FishingBait | None,
) -> list[tuple[str, int]]:
    drops: list[tuple[str, int]] = []
    tier_value = TIER_ORDER.get(tier, 0)
    chance_bonus = gear.bonus_drop_bonus + (bait.bonus_drop_bonus if bait else 0)
    if spot.id == "anomaly":
        chance_bonus += 1
    for drop in BONUS_DROPS:
        if spot.id not in drop["spots"]:
            continue
        if tier_value < TIER_ORDER.get(str(drop.get("min_tier") or "junk"), 0):
            continue
        chance = max(0, int(drop["chance"]) + chance_bonus)
        if rng.randint(1, 100) <= chance:
            drops.append((str(drop["name"]), int(drop.get("qty", 1) or 1)))
    return drops


def _fish_candidates(tier: str, spot: FishingSpot, bait: FishingBait | None) -> list[FishSpecies]:
    candidates = [
        fish for fish in FISH_SPECIES
        if fish.tier == tier and spot.id in fish.spots
    ]
    if bait:
        preferred = [fish for fish in candidates if bait.name in fish.bait_bonus]
        if preferred:
            candidates.extend(preferred)
    if candidates:
        return candidates
    fallback_tiers = ["common", "uncommon", "rare"]
    for fallback in fallback_tiers:
        candidates = [
            fish for fish in FISH_SPECIES
            if fish.tier == fallback and spot.id in fish.spots
        ]
        if candidates:
            return candidates
    return [FISH_SPECIES[0]]


def _roll_fish_entry(fish: FishSpecies, spot: FishingSpot, rng: random.Random) -> dict:
    weight = round(rng.uniform(fish.weight_min, fish.weight_max), 2)
    price_per_kg = rng.randint(fish.price_per_kg_min, fish.price_per_kg_max)
    value = max(1, int(round(weight * price_per_kg)))
    return {
        "name": fish.name,
        "tier": fish.tier,
        "weight_kg": weight,
        "price_per_kg": price_per_kg,
        "value": value,
        "spot": spot.id,
        "caught_at": _now(),
    }


def _early_bite_chance(
    elapsed: int,
    duration: int,
    player,
    gear: FishingGear,
    bait: FishingBait | None,
) -> int:
    if elapsed < 30:
        return 0
    progress = max(0.0, min(0.99, elapsed / max(1, duration)))
    progress_bonus = max(0, int((progress - 0.20) * 55))
    stat_bonus = min(30, _stat(player, "luck") * 3 + _stat(player, "perception"))
    gear_bonus = min(12, gear.tier * 3)
    bait_bonus = 5 if bait else 0
    return max(5, min(70, 5 + progress_bonus + stat_bonus + gear_bonus + bait_bonus))


def _roll_early_bite(
    elapsed: int,
    duration: int,
    player,
    gear: FishingGear,
    bait: FishingBait | None,
    seed: int,
    checks_done: int,
) -> tuple[bool, int]:
    chance = _early_bite_chance(elapsed, duration, player, gear, bait)
    if chance <= 0:
        return False, 0
    rng = random.Random(seed + 17 + checks_done * 7919)
    return rng.randint(1, 100) <= chance, chance


def _format_fish_entry(entry: dict) -> str:
    return (
        f"• {entry['name']} {float(entry['weight_kg']):.2f} кг "
        f"({int(entry['value'])} руб.)"
    )


def _adjust_fish_entry(entry: dict, quality_pct: int) -> dict:
    adjusted = dict(entry)
    quality = max(65, min(125, int(quality_pct)))
    adjusted["weight_kg"] = round(float(adjusted["weight_kg"]) * quality / 100, 2)
    adjusted["value"] = max(1, int(round(adjusted["value"] * quality / 100)))
    adjusted["fight_quality"] = quality
    return adjusted


def _fight_signal(seed: int, turn: int) -> str:
    signals = ("jerk", "bottom", "tremble")
    return signals[random.Random(seed + turn * 37).randint(0, len(signals) - 1)]


def _format_fight_signal(signal: str, perception: int) -> str:
    descriptions = {
        "jerk": "Рыба резко рванула в сторону.",
        "bottom": "Леска тяжелеет: рыба давит ко дну.",
        "tremble": "По леске идёт короткая дрожь.",
    }
    hints = {
        "jerk": "Риск срыва высокий, быстрые действия опаснее обычного.",
        "bottom": "Рыба тяжёлая, ошибка сильнее бьёт по качеству.",
        "tremble": "Окно стабильнее обычного, но рыба ещё может обмануть.",
    }
    text = descriptions.get(signal, descriptions["tremble"])
    if perception >= 7:
        text += f"\nНаблюдение: {hints.get(signal, hints['tremble'])}"
    return text


def _fight_turns_for(tier: str, early_success: bool, fish_entry: dict | None = None) -> int:
    weight = float((fish_entry or {}).get("weight_kg", 0) or 0)
    turns = 2
    if tier == "rare":
        turns += 2
    elif tier == "uncommon":
        turns += 1
    if early_success:
        turns += 1
    if weight >= 2.0:
        turns += 1
    if weight >= 4.0:
        turns += 1
    if weight >= 6.0:
        turns += 1
    return min(7, max(2, turns))


def _should_start_fight(tier: str, early_success: bool, fish_entry: dict, rng: random.Random) -> bool:
    if early_success:
        return True
    if tier == "rare":
        return True
    if tier == "uncommon" and rng.randint(1, 100) <= 35:
        return True
    return int(fish_entry.get("value", 0) or 0) >= 350 and rng.randint(1, 100) <= 50


def _fish_required_gear_tier(tier: str, spot_id: str, weight_kg: float) -> int:
    required = {"common": 0, "uncommon": 2, "rare": 3}.get(tier, 1)
    if spot_id == "deep":
        required += 1
    elif spot_id == "anomaly":
        required += 2
    if weight_kg >= 3.0:
        required += 1
    if weight_kg >= 5.0:
        required += 1
    return min(5, required)


def _gear_gap_for_fish(gear: FishingGear, fish_entry: dict) -> int:
    required = _fish_required_gear_tier(
        str(fish_entry.get("tier") or "common"),
        str(fish_entry.get("spot") or ""),
        float(fish_entry.get("weight_kg", 0) or 0),
    )
    return max(0, required - int(gear.tier))


def _fight_action_profile(move: str) -> dict:
    return {
        "pull": {"control": -6, "quality": 8, "progress": 1, "risk": 20},
        "hold": {"control": 9, "quality": 2, "progress": 1, "risk": 12},
        "release": {"control": 15, "quality": -5, "progress": 0, "risk": 8},
        "surge": {"control": -14, "quality": 4, "progress": 2, "risk": 38},
    }.get(move, {"control": 0, "quality": 0, "progress": 1, "risk": 20})


def _fight_signal_pressure(signal: str, move: str) -> dict:
    pressure = {
        "jerk": {
            "pull": {"risk": 22, "control": -12, "quality": -5},
            "hold": {"risk": 8, "control": -2, "quality": 1},
            "release": {"risk": -10, "control": 8, "quality": -3},
            "surge": {"risk": 24, "control": -14, "quality": -8},
        },
        "bottom": {
            "pull": {"risk": 8, "control": -4, "quality": 4},
            "hold": {"risk": -6, "control": 7, "quality": 2},
            "release": {"risk": 4, "control": 3, "quality": -8},
            "surge": {"risk": 12, "control": -8, "quality": 0},
        },
        "tremble": {
            "pull": {"risk": -4, "control": -1, "quality": 5},
            "hold": {"risk": -2, "control": 4, "quality": 0},
            "release": {"risk": 8, "control": 5, "quality": -7},
            "surge": {"risk": -2, "control": -7, "quality": 2},
        },
    }
    return pressure.get(signal, {}).get(move, {"risk": 0, "control": 0, "quality": 0})


def _resolve_fight_action(
    player,
    state: dict,
    move: str,
    signal: str,
    gear: FishingGear,
) -> dict:
    profile = _fight_action_profile(move)
    pressure = _fight_signal_pressure(signal, move)
    control = max(0, min(100, int(state.get("control", 50) or 50)))
    quality = max(65, min(125, int(state.get("quality_pct", 100) or 100)))
    seed = int(state.get("seed", 0) or 0)
    turn = int(state.get("turn", 0) or 0)
    rng = random.Random(seed + turn * 104729 + len(move) * 97)
    gear_gap = max(0, int(state.get("gear_gap", 0) or 0))

    risk = int(profile["risk"]) + int(pressure["risk"])
    risk += max(0, 45 - control) // 2
    risk += gear_gap * (12 if move == "surge" else 8)
    risk -= min(14, _stat(player, "luck") + gear.tier * 2)
    risk = max(5, min(85, risk))

    stumble = rng.randint(1, 100) <= risk
    swing = rng.randint(-4, 4)
    if stumble:
        control_delta = int(profile["control"]) + int(pressure["control"]) - rng.randint(8, 18)
        quality_delta = int(profile["quality"]) + int(pressure["quality"]) - rng.randint(6, 16) - gear_gap * 5
        note = (
            "Рывок вышел грубо: рыба ответила сильнее и сбила качество."
            if move == "surge"
            else "Рыба сбила темп: решение не провалилось полностью, но улов потерял качество."
        )
    else:
        control_delta = int(profile["control"]) + int(pressure["control"]) + rng.randint(0, 8)
        quality_delta = int(profile["quality"]) + int(pressure["quality"]) + swing - gear_gap * 2
        note = (
            "Рывок ускорил вываживание, но рыба ещё может сорваться на слабой снасти."
            if move == "surge"
            else "Ты удержал ситуацию, но рыба всё ещё сопротивляется."
        )

    return {
        "control": max(0, min(100, control + control_delta - gear_gap * 3)),
        "quality": max(65, min(125 - gear_gap * 10, quality + quality_delta)),
        "progress": int(profile["progress"]),
        "risk": risk,
        "stumble": stumble,
        "note": note,
    }


def _send_fight_prompt(player, vk, user_id: int, state: dict, intro: str | None = None):
    from handlers.keyboards import create_fishing_fight_keyboard

    signal = str(state.get("signal") or "tremble")
    fish_entry = state.get("fish_entry") or {}
    lines = [
        intro or "🎣 На крючке сильная рыба.",
        "",
        _format_fight_signal(signal, _stat(player, "perception")),
        "",
        f"Натяжение: {int(state.get('control', 50) or 50)}/100.",
        f"Осталось ходов: {int(state.get('turns_left', 1) or 1)}.",
        f"На кону: {fish_entry.get('name', 'рыба')} примерно {float(fish_entry.get('weight_kg', 0) or 0):.2f} кг.",
    ]
    gear_gap = int(state.get("gear_gap", 0) or 0)
    if gear_gap >= 2:
        lines.append("Снасть на пределе: резкие действия могут сорвать рыбу.")
    elif gear_gap == 1:
        lines.append("Снасть справляется тяжело: лучше не жадничать с рывками.")
    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=create_fishing_fight_keyboard().get_keyboard(),
        random_id=0,
    )


def _start_fishing_fight(
    player,
    vk,
    user_id: int,
    state: dict,
    fish_entry: dict,
    xp_gain: int,
    tier: str,
    hazard: bool,
    bonus_rewards: list[tuple[str, int]],
    gear: FishingGear,
    bait: FishingBait | None,
    seed: int,
    early_success: bool,
) -> bool:
    gear_gap = _gear_gap_for_fish(gear, fish_entry)
    if gear_gap >= 4:
        return _finish_fishing_escape(
            player,
            vk,
            user_id,
            fish_name=str(fish_entry.get("name") or "рыба"),
            spot=SPOTS.get(str(state.get("spot") or "shore"), SPOTS["shore"]),
            gear=gear,
            bait=bait,
            bonus_rewards=bonus_rewards,
            reason="рыба слишком крупная и сильная для этой снасти.",
        )

    turns = _fight_turns_for(tier, early_success, fish_entry) + min(2, gear_gap)
    fight_state = {
        "mode": "fight",
        "fish_entry": fish_entry,
        "xp_gain": int(xp_gain),
        "tier": tier,
        "hazard": bool(hazard),
        "spot": str(state.get("spot") or "shore"),
        "gear": gear.name,
        "gear_label": gear.label,
        "bait": bait.name if bait else "",
        "bait_label": bait.label if bait else "",
        "bonus_rewards": [[name, qty] for name, qty in bonus_rewards],
        "seed": seed,
        "turn": 0,
        "turns_left": turns,
        "control": max(25, 55 + min(20, _stat(player, "luck") + gear.tier * 3) - gear_gap * 10),
        "quality_pct": max(70, 100 - gear_gap * 5),
        "gear_gap": gear_gap,
        "signal": _fight_signal(seed, 0),
    }
    _set_state(user_id, fight_state)
    _send_fight_prompt(
        player,
        vk,
        user_id,
        fight_state,
        intro="🎣 Резкая поклёвка. Похоже, на крючке что-то стоящее.",
    )
    return True


def _finish_fishing_result(
    player,
    vk,
    user_id: int,
    *,
    catch_name: str,
    rewards: list[tuple[str, int]],
    xp_gain: int,
    spot: FishingSpot,
    gear: FishingGear,
    bait: FishingBait | None,
    hazard: bool,
    bonus_rewards: list[tuple[str, int]],
    fish_entry: dict | None = None,
    fight_note: str = "",
) -> bool:
    from handlers.keyboards import create_fishing_keyboard

    rng = random.Random(int((fish_entry or {}).get("caught_at") or _now()) + 41)
    reward_lines = []
    if fish_entry:
        locker_result = database.add_fish_to_locker_transaction(user_id, fish_entry, FISH_LOCKER_CAPACITY)
        if locker_result.get("success"):
            reward_lines.append(_format_fish_entry(fish_entry))
        elif locker_result.get("full"):
            reward_lines.append(
                f"• {fish_entry.get('name', catch_name)} сорвалась: рыбный шкаф турбазы заполнен "
                f"({FISH_LOCKER_CAPACITY}/{FISH_LOCKER_CAPACITY})."
            )
        else:
            reward_lines.append(f"• {fish_entry.get('name', catch_name)} сорвалась: не удалось записать улов в БД.")

    for item_name, qty in [*rewards, *bonus_rewards]:
        if item_name in FISH_SPECIES_NAMES:
            continue
        if database.add_item_to_inventory(user_id, item_name, qty):
            reward_lines.append(f"• {item_name} x{qty}")

    hazard_line = ""
    if hazard and spot.id == "anomaly":
        rad_gain = rng.randint(3, 9)
        player.radiation = max(0, int(getattr(player, "radiation", 0) or 0) + rad_gain)
        database.update_user_stats(user_id, radiation=player.radiation)
        hazard_line = f"\n\n⚠️ Заводь вспыхнула под водой: +{rad_gain} рад."
    elif hazard:
        energy_loss = rng.randint(2, 6)
        player.energy = max(0, int(getattr(player, "energy", 0) or 0) - energy_loss)
        database.update_user_stats(user_id, energy=player.energy)
        hazard_line = f"\n\n⚠️ Снасть зацепилась в корягах: -{energy_loss}⚡."

    gained_xp = int(player.add_experience(xp_gain)) if xp_gain > 0 else 0
    _clear_state(user_id)
    invalidate_player_cache(user_id)

    result_text = (
        f"🎣 Рыбалка завершена: {catch_name}.\n\n"
        f"Снасть: {gear.label}.\n"
        f"Наживка: {bait.label if bait else 'без наживки'}."
    )
    if fight_note:
        result_text += f"\n{fight_note}"
    result_text += "\n\nУлов:\n" + ("\n".join(reward_lines) if reward_lines else "• ничего полезного")
    if gained_xp:
        result_text += f"\n\nОпыт: +{gained_xp}."
    result_text += hazard_line

    vk.messages.send(
        user_id=user_id,
        message=result_text,
        keyboard=create_fishing_keyboard(active=False).get_keyboard(),
        random_id=0,
    )
    return True


def _finish_fishing_escape(
    player,
    vk,
    user_id: int,
    *,
    fish_name: str,
    spot: FishingSpot,
    gear: FishingGear,
    bait: FishingBait | None,
    bonus_rewards: list[tuple[str, int]],
    reason: str,
) -> bool:
    from handlers.keyboards import create_fishing_keyboard

    reward_lines = []
    for item_name, qty in [reward for reward in bonus_rewards if reward[0] not in FISH_SPECIES_NAMES][:1]:
        if database.add_item_to_inventory(user_id, item_name, qty):
            reward_lines.append(f"• {item_name} x{qty}")

    _clear_state(user_id)
    invalidate_player_cache(user_id)

    result_text = (
        f"🎣 Рыба сорвалась: {fish_name}.\n\n"
        f"Снасть: {gear.label}.\n"
        f"Наживка: {bait.label if bait else 'без наживки'}.\n"
        f"Причина: {reason}\n\n"
        "Улов:\n"
        + ("\n".join(reward_lines) if reward_lines else "• ничего полезного")
    )
    if spot.id == "anomaly":
        result_text += "\n\nАномальная вода плохо прощает слабую снасть."

    vk.messages.send(
        user_id=user_id,
        message=result_text,
        keyboard=create_fishing_keyboard(active=False).get_keyboard(),
        random_id=0,
    )
    return True


def _format_menu(player, active: bool = False) -> str:
    gear = _select_gear(getattr(player, "user_id", 0))
    bait = _select_bait(getattr(player, "user_id", 0))
    keepnet = _get_keepnet(getattr(player, "user_id", 0))
    keepnet_value = sum(int(row.get("value", 0) or 0) for row in keepnet)
    lines = [
        "🎣 ОЗЕРО У ТУРБАЗЫ",
        "",
        "Выбери место ловли. Рыбалка займёт несколько минут и тратит энергию.",
        "",
    ]
    for spot in SPOTS.values():
        lines.append(f"• {spot.label}: {spot.energy_cost}⚡, {spot.description}.")
    lines.extend([
        "",
        f"Снасть: {gear.label}.",
        f"Наживка: {bait.label if bait else 'без наживки'}.",
        f"Рыбный шкаф турбазы: {len(keepnet)} рыбы, оценка {keepnet_value} руб.",
        f"Твои факторы: восприятие {_stat(player, 'perception')}, удача {_stat(player, 'luck')}.",
    ])
    if active:
        lines.append("Сейчас у тебя уже стоит снасть.")
    return "\n".join(lines)


def show_fishing_menu(player, vk, user_id: int):
    from handlers.keyboards import create_fishing_keyboard

    active = _get_state(user_id) is not None
    vk.messages.send(
        user_id=user_id,
        message=_format_menu(player, active=active),
        keyboard=create_fishing_keyboard(active=active).get_keyboard(),
        random_id=0,
    )


def start_fishing(player, vk, user_id: int, spot_id: str):
    from handlers.keyboards import create_fishing_keyboard, create_location_keyboard

    if player.current_location_id != LAKE_LOCATION:
        return False
    if _get_state(user_id):
        return check_fishing(player, vk, user_id)

    spot = SPOTS[spot_id]
    gear = _select_gear(user_id)
    bait = _select_bait(user_id)
    energy = int(getattr(player, "energy", 0) or 0)
    if energy < spot.energy_cost:
        vk.messages.send(
            user_id=user_id,
            message=f"⚡ Не хватает энергии для рыбалки. Нужно {spot.energy_cost}, у тебя {energy}.",
            keyboard=create_fishing_keyboard(active=False).get_keyboard(),
            random_id=0,
        )
        return True

    player.energy = energy - spot.energy_cost
    database.update_user_stats(user_id, energy=player.energy)
    if bait:
        if not database.remove_item_from_inventory(user_id, bait.name, 1):
            bait = None
    started_at = _now()
    duration = FISHING_DURATION_SECONDS
    seed = random.randint(1, 2_000_000_000)
    _set_state(user_id, {
        "started_at": started_at,
        "duration": duration,
        "early_checks": 0,
        "last_check_at": 0,
        "spot": spot.id,
        "gear": gear.name,
        "gear_label": gear.label,
        "bait": bait.name if bait else "",
        "bait_label": bait.label if bait else "",
        "seed": seed,
    })
    vk.messages.send(
        user_id=user_id,
        message=(
            f"🎣 Ты поставил снасть: {spot.label}.\n\n"
            f"Снасть: {gear.label}.\n"
            f"Наживка: {bait.label if bait else 'без наживки'}.\n"
            f"Потрачено: {spot.energy_cost}⚡.\n"
            "Вода у турбазы тихая только сверху. Можно проверять улов раньше, но ранняя поклёвка не гарантирована."
        ),
        keyboard=create_fishing_keyboard(active=True).get_keyboard(),
        random_id=0,
    )
    return True


def check_fishing(player, vk, user_id: int):
    from handlers.keyboards import create_fishing_keyboard

    state = _get_state(user_id)
    if not state:
        show_fishing_menu(player, vk, user_id)
        return True
    if state.get("mode") == "fight":
        _send_fight_prompt(player, vk, user_id, state)
        return True

    now = _now()
    started = int(state.get("started_at", now) or now)
    duration = max(30, int(state.get("duration", FISHING_DURATION_SECONDS) or FISHING_DURATION_SECONDS))
    spot = SPOTS.get(str(state.get("spot") or "shore"), SPOTS["shore"])
    gear_name = str(state.get("gear") or "")
    gear = next((row for row in GEAR if row.name == gear_name), FALLBACK_GEAR)
    bait_name = str(state.get("bait") or "")
    bait = next((row for row in BAITS if row.name == bait_name), None)
    seed = int(state.get("seed") or random.randint(1, 999999))
    finish_at = started + duration
    remaining = finish_at - now
    early_bite_won = False
    if remaining > 0:
        elapsed = max(0, now - started)
        last_check_at = int(state.get("last_check_at", 0) or 0)
        checks_done = max(0, int(state.get("early_checks", 0) or 0))
        if last_check_at and now - last_check_at < 20:
            wait = 20 - (now - last_check_at)
            vk.messages.send(
                user_id=user_id,
                message=(
                    "🎣 Вода ещё не успела успокоиться.\n"
                    f"Проверь через {wait} сек. или дождись уверенного результата: {remaining // 60} мин. {remaining % 60} сек."
                ),
                keyboard=create_fishing_keyboard(active=True).get_keyboard(),
                random_id=0,
            )
            return True

        early_success, chance = _roll_early_bite(elapsed, duration, player, gear, bait, seed, checks_done)
        state["early_checks"] = checks_done + 1
        state["last_check_at"] = now
        _set_state(user_id, state)
        if early_success:
            early_bite_won = True
            remaining = 0
        else:
            chance_text = f"Шанс ранней поклёвки был около {chance}%." if chance else "Снасть стоит слишком недавно."
            vk.messages.send(
                user_id=user_id,
                message=(
                    "🎣 Поплавок пока молчит.\n"
                    f"{chance_text}\n"
                    f"Уверенный результат будет через {remaining // 60} мин. {remaining % 60} сек."
                ),
                keyboard=create_fishing_keyboard(active=True).get_keyboard(),
                random_id=0,
            )
            return True

    tier, hazard = _pick_tier(player, spot, seed, gear, bait)
    rng = random.Random(seed + 29)

    if tier == "junk":
        catch_name, rewards, xp_gain = rng.choice(JUNK_CATCHES["junk"])
        fish_entry = None
    else:
        fish = rng.choice(_fish_candidates(tier, spot, bait))
        fish_entry = _roll_fish_entry(fish, spot, rng)
        catch_name = fish.name
        rewards = []
        xp_gain = fish.xp

    bonus_rewards = _roll_bonus_drops(spot, tier, rng, gear, bait)
    if fish_entry and _should_start_fight(tier, early_bite_won, fish_entry, rng):
        return _start_fishing_fight(
            player, vk, user_id, state, fish_entry, xp_gain, tier, hazard,
            bonus_rewards, gear, bait, seed, early_bite_won,
        )

    return _finish_fishing_result(
        player,
        vk,
        user_id,
        catch_name=catch_name,
        rewards=rewards,
        xp_gain=xp_gain,
        spot=spot,
        gear=gear,
        bait=bait,
        hazard=hazard,
        bonus_rewards=bonus_rewards,
        fish_entry=fish_entry,
    )


def cancel_fishing(player, vk, user_id: int):
    from handlers.keyboards import create_fishing_keyboard

    if _get_state(user_id):
        _clear_state(user_id)
        message = "🎣 Ты смотал снасть. Потраченную энергию уже не вернуть."
    else:
        message = "🎣 Сейчас у тебя нет активной рыбалки."
    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=create_fishing_keyboard(active=False).get_keyboard(),
        random_id=0,
    )
    return True


def handle_fishing_fight_action(player, vk, user_id: int, action: str) -> bool:
    state = _get_state(user_id)
    if not state or state.get("mode") != "fight":
        return False

    normalized = (action or "").strip().lower()
    action_map = {
        "вываживать": "pull",
        "тянуть": "pull",
        "удерживать": "hold",
        "держать": "hold",
        "стравить леску": "release",
        "стравить": "release",
        "ослабить": "release",
        "отпустить": "release",
        "рывок": "surge",
        "резкий рывок": "surge",
        "подсечь": "surge",
    }
    move = action_map.get(normalized)
    if not move:
        return False

    spot = SPOTS.get(str(state.get("spot") or "shore"), SPOTS["shore"])
    gear_name = str(state.get("gear") or "")
    gear = next((row for row in GEAR if row.name == gear_name), FALLBACK_GEAR)
    bait_name = str(state.get("bait") or "")
    bait = next((row for row in BAITS if row.name == bait_name), None)
    signal = str(state.get("signal") or "tremble")
    outcome = _resolve_fight_action(player, state, move, signal, gear)
    turns_left = max(0, int(state.get("turns_left", 1) or 1) - int(outcome["progress"]))
    gear_gap = max(0, int(state.get("gear_gap", 0) or 0))

    state["control"] = outcome["control"]
    state["quality_pct"] = outcome["quality"]
    state["turns_left"] = turns_left
    state["turn"] = int(state.get("turn", 0) or 0) + 1
    state["signal"] = _fight_signal(int(state.get("seed", 0) or 0), int(state["turn"]))

    escape_roll = random.Random(int(state.get("seed", 0) or 0) + int(state["turn"]) * 65537 + 13)
    escape_chance = 0
    if gear_gap >= 2 and outcome["stumble"]:
        escape_chance += 18 * gear_gap
    if state["control"] <= 0:
        escape_chance += 45 + gear_gap * 15
    if move == "surge" and gear_gap:
        escape_chance += 10 * gear_gap
    escape_chance = min(95, escape_chance)
    if escape_chance and escape_roll.randint(1, 100) <= escape_chance:
        return _finish_fishing_escape(
            player,
            vk,
            user_id,
            fish_name=str((state.get("fish_entry") or {}).get("name") or "рыба"),
            spot=spot,
            gear=gear,
            bait=bait,
            bonus_rewards=[(str(name), int(qty)) for name, qty in state.get("bonus_rewards", [])],
            reason=f"снасть не выдержала рывок ({escape_chance}% риска срыва).",
        )

    if turns_left > 0 and state["control"] > 0:
        _set_state(user_id, state)
        _send_fight_prompt(player, vk, user_id, state, intro=f"🎣 {outcome['note']} Риск хода был около {outcome['risk']}%.")
        return True

    fish_entry = _adjust_fish_entry(dict(state.get("fish_entry") or {}), int(state["quality_pct"]))
    final_note = f"Вываживание: {outcome['note']} Качество улова {int(state['quality_pct'])}%."
    if state["control"] <= 0:
        final_note = "Вываживание: рыба почти сорвалась, но ты вытащил её на берег. Качество улова 65%."
        fish_entry = _adjust_fish_entry(dict(state.get("fish_entry") or {}), 65)

    return _finish_fishing_result(
        player,
        vk,
        user_id,
        catch_name=str(fish_entry.get("name") or "рыба"),
        rewards=[],
        xp_gain=int(state.get("xp_gain", 0) or 0),
        spot=spot,
        gear=gear,
        bait=bait,
        hazard=bool(state.get("hazard")),
        bonus_rewards=[(str(name), int(qty)) for name, qty in state.get("bonus_rewards", [])],
        fish_entry=fish_entry,
        fight_note=final_note,
    )


def show_cooking_menu(player, vk, user_id: int):
    from handlers.keyboards import create_location_keyboard

    recipe_lines = []
    for recipe in COOKING_RECIPES.values():
        any_parts = [group["label"] for group in recipe.get("ingredients_any", {}).values()]
        fixed_parts = [f"{name} x{qty}" for name, qty in recipe.get("ingredients", [])]
        recipe_lines.append(f"• {recipe['label']}: {', '.join([*any_parts, *fixed_parts])}.")
    vk.messages.send(
        user_id=user_id,
        message=(
            "🍲 КУХНЯ ТУРБАЗЫ\n\n"
            "Доступные рецепты:\n"
            + "\n".join(recipe_lines)
            + "\n\n"
            "Команда: приготовить уху."
        ),
        keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
        random_id=0,
    )
    return True


def show_fish_locker(player, vk, user_id: int):
    from handlers.keyboards import create_location_keyboard

    entries = _get_keepnet(user_id)
    total_value = sum(max(0, int(row.get("value", 0) or 0)) for row in entries)
    total_weight = sum(max(0.0, float(row.get("weight_kg", 0) or 0)) for row in entries)
    lines = [
        "🗄️ РЫБНЫЙ ШКАФ ТУРБАЗЫ",
        "",
        f"Заполнено: {len(entries)}/{FISH_LOCKER_CAPACITY}.",
        f"Вес: {total_weight:.2f} кг.",
        f"Оценка Лучика: {total_value} руб.",
    ]
    if entries:
        lines.extend(["", "Самое ценное:"])
        for entry in sorted(entries, key=lambda row: int(row.get("value", 0) or 0), reverse=True)[:12]:
            lines.append(_format_fish_entry(entry))
        if len(entries) > 12:
            lines.append(f"• ещё {len(entries) - 12} шт.")
    else:
        lines.extend(["", "Шкаф пуст. Рыба с озера будет складываться сюда, а не в рюкзак."])
    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
        random_id=0,
    )
    return True


def show_luchik_shop(player, vk, user_id: int):
    from handlers.keyboards import create_location_keyboard

    lines = ["🎣 СНАСТИ У ЛУЧИКА", ""]
    for idx, item_name in enumerate(LUCHIK_SHOP_ITEMS, 1):
        item = database.get_item_by_name(item_name) or {}
        price = int(item.get("price", 0) or 0)
        requirement = LUCHIK_ROD_UPGRADES.get(item_name)
        if requirement:
            req_text = _format_item_requirements(requirement["requires"])
            lines.append(f"{idx}. {item_name} — {price} руб. + {req_text}")
        else:
            lines.append(f"{idx}. {item_name} — {price} руб.")
    lines.extend(["", "Команды: купить 2 черви, купить старая удочка."])
    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
        random_id=0,
    )
    return True


def _buy_luchik_rod_upgrade(player, user_id: int, item_name: str) -> tuple[bool, str]:
    requirement = LUCHIK_ROD_UPGRADES.get(item_name)
    if not requirement:
        return player.buy_item(item_name)

    required_items = list(requirement.get("requires") or [])
    quantities = _inventory_quantities(user_id, [name for name, _ in required_items])
    missing = [
        f"{name} x{qty - quantities.get(name, 0)}"
        for name, qty in required_items
        if quantities.get(name, 0) < qty
    ]
    if missing:
        return False, "Не хватает для апгрейда: " + ", ".join(missing) + "."

    removed: list[tuple[str, int]] = []
    for name, qty in required_items:
        if not database.remove_item_from_inventory(user_id, name, qty):
            for restored_name, restored_qty in removed:
                database.add_item_to_inventory(user_id, restored_name, restored_qty)
            return False, f"Не удалось списать компонент: {name}."
        removed.append((name, qty))

    success, message = player.buy_item(item_name)
    if not success:
        for restored_name, restored_qty in removed:
            database.add_item_to_inventory(user_id, restored_name, restored_qty)
        return False, message

    return True, (
        f"{message}\n"
        f"Списано для апгрейда: {_format_item_requirements(required_items)}."
    )


def buy_luchik_shop_item(player, vk, user_id: int, payload: str):
    from handlers.keyboards import create_location_keyboard

    raw = (payload or "").strip().lower()
    if not raw:
        show_luchik_shop(player, vk, user_id)
        return True

    qty = 1
    parts = raw.split(maxsplit=1)
    if parts and parts[0].isdigit():
        qty = max(1, min(20, int(parts[0])))
        raw = parts[1].strip() if len(parts) > 1 else ""

    item_name = None
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(LUCHIK_SHOP_ITEMS):
            item_name = LUCHIK_SHOP_ITEMS[idx - 1]
    if not item_name:
        item_name = next((name for name in LUCHIK_SHOP_ITEMS if raw == name.lower()), None)
    if not item_name:
        item_name = next((name for name in LUCHIK_SHOP_ITEMS if raw and raw in name.lower()), None)
    if not item_name:
        message = "У Лучика такого товара нет. Команда: снасти."
    elif item_name in LUCHIK_ROD_UPGRADES and qty > 1:
        message = "Удочки улучшаются по одной. Команда: купить складная удочка."
    else:
        bought = 0
        last_message = ""
        for _ in range(qty):
            if item_name in LUCHIK_ROD_UPGRADES:
                success, last_message = _buy_luchik_rod_upgrade(player, user_id, item_name)
            else:
                success, last_message = player.buy_item(item_name)
            if not success:
                break
            bought += 1
        if bought <= 0:
            message = last_message or "Покупка не прошла."
        elif item_name in LUCHIK_ROD_UPGRADES and bought == 1:
            message = last_message
        elif bought == qty:
            message = f"Куплено: {item_name} x{bought}.\nДенег сейчас: {player.money} руб."
        else:
            message = f"Куплено: {item_name} x{bought}.\nДальше не вышло: {last_message}"
        if bought:
            invalidate_player_cache(user_id)

    vk.messages.send(
        user_id=user_id,
        message=f"🎣 Старик Лучик:\n\n{message}",
        keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
        random_id=0,
    )
    return True


def cook_recipe(player, vk, user_id: int, recipe_id: str):
    from handlers.keyboards import create_location_keyboard

    recipe = COOKING_RECIPES.get(recipe_id)
    if not recipe:
        result = {"success": False, "message": "Такого рецепта на кухне пока нет."}
    else:
        recipe_for_db, locker_groups = _fish_any_groups(recipe)
        consumed: list[dict] = []
        used_parts: list[str] = []
        result = {"success": False, "message": "Не хватает рыбы в шкафу турбазы."}
        for group in locker_groups:
            ok, used_text, selected = _consume_fish_from_keepnet(
                user_id,
                tuple(group.get("items") or ()),
                int(group.get("qty", 1) or 1),
            )
            if not ok:
                _restore_keepnet(user_id, consumed)
                result = {"success": False, "message": f"Не хватает: {group.get('label', 'рыба')} в рыбном шкафу турбазы."}
                break
            consumed.extend(selected)
            used_parts.append(used_text)
        else:
            result = database.cook_luchik_recipe_transaction(user_id, recipe_for_db)
            if result.get("success") and used_parts:
                base_message = str(result.get("message", "Готово.")).rstrip(".")
                result["message"] = f"{base_message}. Из рыбного шкафа: {', '.join(used_parts)}."
            elif not result.get("success"):
                _restore_keepnet(user_id, consumed)
    if result.get("success"):
        invalidate_player_cache(user_id)
    vk.messages.send(
        user_id=user_id,
        message=f"🍲 Старик Лучик:\n\n{result.get('message', 'Котелок сегодня молчит.')}",
        keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
        random_id=0,
    )
    return True


def _format_luchik_orders(user_id: int) -> str:
    lines = ["📋 ЗАКАЗЫ ЛУЧИКА", ""]
    for order_id, order in LUCHIK_ORDERS.items():
        done = int(database.get_user_flag(user_id, order["flag"], 0) or 0) > 0
        status = "выполнен" if done else "можно сдать"
        reward_items = ", ".join(f"{name} x{qty}" for name, qty in order.get("reward_items", []))
        reward_text = f"{order['reward_money']} руб." + (f", {reward_items}" if reward_items else "")
        lines.append(f"• {order['label']} ({status})")
        lines.append(f"  Нужно: {order['description']}; награда: {reward_text}.")
        command = tuple(order.get("commands", (f"заказ {order_id}",)))[0]
        lines.append(f"  Команда: {command}.")
    return "\n".join(lines)


def show_luchik_orders(player, vk, user_id: int):
    from handlers.keyboards import create_location_keyboard

    vk.messages.send(
        user_id=user_id,
        message=_format_luchik_orders(user_id),
        keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
        random_id=0,
    )
    return True


def complete_luchik_order(player, vk, user_id: int, order_id: str):
    from handlers.keyboards import create_location_keyboard

    order = LUCHIK_ORDERS.get(order_id)
    if not order:
        result = {"success": False, "message": "Лучик такого заказа не помнит."}
    else:
        order_items = tuple(order.get("items") or ())
        if order_items and set(order_items).issubset(FISH_SPECIES_NAMES):
            ok, used_text, consumed = _consume_fish_from_keepnet(user_id, order_items, int(order.get("qty", 1) or 1))
            if not ok:
                result = {"success": False, "message": f"Не хватает улова в рыбном шкафу для заказа «{order.get('label', 'заказ')}»."}
            else:
                order_for_db = dict(order)
                order_for_db["items"] = ()
                order_for_db["qty"] = 0
                result = database.complete_luchik_order_transaction(user_id, order_for_db)
                if result.get("success"):
                    result["message"] = result.get("message", "Заказ закрыт.").replace(
                        "Списано: ничего.",
                        f"Списано из рыбного шкафа: {used_text}.",
                    )
                else:
                    _restore_keepnet(user_id, consumed)
        else:
            result = database.complete_luchik_order_transaction(user_id, order)
        if result.get("success"):
            invalidate_player_cache(user_id)
    vk.messages.send(
        user_id=user_id,
        message=f"📋 Старик Лучик:\n\n{result.get('message', 'Заказ не сдан.')}",
        keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
        random_id=0,
    )
    return True


def sell_luchik_fish(player, vk, user_id: int, npc_id: str):
    """Продать Лучику рыбу из рыбного шкафа турбазы и legacy-рыбу из инвентаря."""
    from handlers.keyboards import create_npc_dialog_keyboard

    setattr(player, "_luchik_last_sale_success", False)
    locker_sale = database.sell_fish_locker_transaction(user_id)
    sold_lines = [
        f"• {row.get('name', 'Рыба')} {float(row.get('weight_kg', 0) or 0):.2f} кг — {int(row.get('value', 0) or 0)} руб."
        for row in locker_sale.get("sold", [])
    ] if locker_sale.get("success") else []
    locker_total = int(locker_sale.get("total", 0) or 0) if locker_sale.get("success") else 0
    new_balance = int(locker_sale.get("remaining_money", 0) or 0) if locker_sale.get("success") else None

    legacy = database.sell_luchik_fish_transaction(user_id)
    if legacy.get("success"):
        for row in legacy.get("sold", []):
            sold_lines.append(f"• {row['name']} x{row['quantity']} — {row['amount']} руб.")
        new_balance = int(legacy.get("remaining_money", new_balance or 0) or 0)

    total = locker_total + (int(legacy.get("total", 0) or 0) if legacy.get("success") else 0)
    if total <= 0:
        message = legacy.get("message") if legacy.get("message") != "У тебя нет рыбы, которую берёт Лучик." else locker_sale.get("message")
        message = message or "У тебя нет рыбы, которую берёт Лучик."
    else:
        invalidate_player_cache(user_id)
        setattr(player, "_luchik_last_sale_success", True)
        if new_balance is not None:
            player.money = int(new_balance)
        message = (
            "Он взвешивает рыбу по одной, сверяет записи в мокром журнале и откладывает редкое отдельно.\n\n"
            f"{chr(10).join(sold_lines)}\n\n"
            f"Итого: {total} руб."
        )
        if new_balance is not None:
            message += f"\nДенег сейчас: {new_balance} руб."

    vk.messages.send(
        user_id=user_id,
        message=f"🎣Старик Лучик:\n\n{message}",
        keyboard=create_npc_dialog_keyboard(npc_id).get_keyboard(),
        random_id=0,
    )
    return True


def handle_fishing_command(player, vk, user_id: int, text: str) -> bool:
    normalized = (text or "").strip().lower()
    if normalized in {"рыбачить", "рыбалка", "озеро"}:
        show_fishing_menu(player, vk, user_id)
        return True
    if normalized in {
        "вываживать", "тянуть",
        "удерживать", "держать",
        "стравить леску", "стравить", "отпустить", "ослабить",
        "рывок", "резкий рывок", "подсечь",
    }:
        return handle_fishing_fight_action(player, vk, user_id, normalized)
    if normalized in {"проверить улов", "проверить рыбалку", "проверить", "улов"}:
        return check_fishing(player, vk, user_id)
    if normalized in {"отменить рыбалку", "отмена рыбалки", "смотать снасть", "отмена", "стоп"}:
        return cancel_fishing(player, vk, user_id)
    if normalized in {"рыбный шкаф", "шкаф рыбы", "улов в шкафу", "шкаф"}:
        return show_fish_locker(player, vk, user_id)
    spot_id = SPOT_ALIASES.get(normalized)
    if spot_id:
        return start_fishing(player, vk, user_id, spot_id)
    return False


def handle_tourbase_command(player, vk, user_id: int, text: str) -> bool:
    normalized = (text or "").strip().lower()
    if normalized in {"рыбный шкаф", "шкаф рыбы", "улов в шкафу"}:
        return show_fish_locker(player, vk, user_id)
    if normalized in {"снасти", "магазин лучика", "рыболовный магазин", "магазин"}:
        return show_luchik_shop(player, vk, user_id)
    if normalized.startswith("купить "):
        return buy_luchik_shop_item(player, vk, user_id, normalized.replace("купить ", "", 1))
    if normalized in {"готовка", "кухня", "готовить"}:
        return show_cooking_menu(player, vk, user_id)
    for recipe_id, recipe in COOKING_RECIPES.items():
        if normalized in recipe.get("commands", set()):
            return cook_recipe(player, vk, user_id, recipe_id)
    if normalized in {"заказы", "заказы лучика", "заказ"}:
        return show_luchik_orders(player, vk, user_id)
    for order_id, order in LUCHIK_ORDERS.items():
        if normalized in order.get("commands", ()):
            return complete_luchik_order(player, vk, user_id, order_id)
    if normalized.startswith("заказ "):
        return complete_luchik_order(player, vk, user_id, normalized.replace("заказ ", "", 1).strip())
    return False
