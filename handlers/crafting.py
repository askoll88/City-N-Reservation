"""
Обработчики крафта в убежище.
"""
from __future__ import annotations

from game.crafting import (
    CRAFTING_MAX_LEVEL,
    CRAFT_RECIPES,
    add_crafting_xp,
    get_crafting_progress,
    get_recipe_by_index,
)
from handlers.keyboards import create_location_keyboard
from infra import database


def _recipe_line(recipe: dict, idx: int, player_level: int) -> str:
    req_level = int(recipe["required_level"])
    icon = "🔓" if player_level >= req_level else "🔒"
    ingredients = " + ".join(f"{name} x{qty}" for name, qty in recipe["ingredients"])
    result_name, result_qty = recipe["result"]
    lock_note = "" if player_level >= req_level else f" (нужен {req_level} ур.)"
    return f"{icon} {idx}. {recipe['name']}{lock_note}\n   {ingredients} -> {result_name} x{result_qty}"


def show_crafting_menu(player, vk, user_id: int):
    if player.current_location_id != "убежище":
        vk.messages.send(
            user_id=user_id,
            message="Крафт доступен только в убежище.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    progress = get_crafting_progress(user_id)
    level = int(progress["level"])
    xp = int(progress["xp"])
    next_threshold = int(progress["next_threshold"])

    if level >= CRAFTING_MAX_LEVEL:
        progress_line = f"Навык крафта: {level}/{CRAFTING_MAX_LEVEL} (максимум)"
    else:
        progress_line = f"Навык крафта: {level}/{CRAFTING_MAX_LEVEL} ({xp}/{next_threshold} XP)"

    lines = [
        "🛠️ ВЕРСТАК УБЕЖИЩА",
        progress_line,
        "",
        "Рецепты:",
    ]
    for idx, recipe in enumerate(CRAFT_RECIPES, 1):
        lines.append(_recipe_line(recipe, idx, level))

    lines.append("")
    lines.append("Команды:")
    lines.append("• скрафтить <номер>")
    lines.append("• скрафтить <название рецепта>")

    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
        random_id=0,
    )


def _find_recipe_by_text(target: str) -> dict | None:
    if not target:
        return None
    raw = target.strip()
    if raw.isdigit():
        return get_recipe_by_index(int(raw))

    lowered = raw.lower()
    for recipe in CRAFT_RECIPES:
        if lowered == recipe["name"].lower():
            return recipe
    return None


def craft_recipe(player, vk, user_id: int, target: str):
    if player.current_location_id != "убежище":
        vk.messages.send(
            user_id=user_id,
            message="Крафт доступен только в убежище.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    recipe = _find_recipe_by_text(target)
    if not recipe:
        vk.messages.send(
            user_id=user_id,
            message="Рецепт не найден. Открой 'Крафт' и выбери номер рецепта.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    progress = get_crafting_progress(user_id)
    craft_level = int(progress["level"])
    required_level = int(recipe["required_level"])
    if craft_level < required_level:
        vk.messages.send(
            user_id=user_id,
            message=(
                f"🔒 Рецепт '{recipe['name']}' пока недоступен.\n"
                f"Нужен навык крафта {required_level}, у тебя {craft_level}."
            ),
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    result_name, result_qty = recipe["result"]
    tx = database.craft_item_transaction(
        vk_id=user_id,
        ingredients=recipe["ingredients"],
        result_item_name=result_name,
        result_quantity=result_qty,
    )
    if not tx.get("success"):
        vk.messages.send(
            user_id=user_id,
            message=f"❌ {tx.get('message', 'Крафт не удался.')}",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    gain = add_crafting_xp(user_id, int(recipe.get("xp_gain", 0) or 0))
    level_up_msg = ""
    if gain["new_level"] > gain["old_level"]:
        level_up_msg = f"\n🎯 Навык крафта повышен: {gain['old_level']} -> {gain['new_level']}"

    ingredients_text = ", ".join(f"{name} x{qty}" for name, qty in recipe["ingredients"])
    vk.messages.send(
        user_id=user_id,
        message=(
            f"✅ Скрафчено: {result_name} x{result_qty}\n"
            f"Списано: {ingredients_text}\n"
            f"Опыт крафта: +{gain['gained']} (всего {gain['new_xp']})"
            f"{level_up_msg}"
        ),
        keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
        random_id=0,
    )
