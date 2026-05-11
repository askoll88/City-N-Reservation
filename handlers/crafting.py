"""
Обработчики крафта в убежище.
"""
from __future__ import annotations

from vk_api.keyboard import VkKeyboard, VkKeyboardColor

from game import ui
from game.crafting import (
    CRAFTING_MAX_LEVEL,
    CRAFT_RECIPES,
    add_crafting_xp,
    get_crafting_progress,
    get_recipe_by_index,
)
from game.weapon_progression import ASCENSION_MATERIALS, WEAPON_XP_MATERIALS
from handlers.keyboards import (
    create_location_keyboard,
    create_weapon_upgrade_keyboard,
    create_workbench_keyboard,
)
from infra import database
from infra.state_manager import try_edit_or_send_ui


CRAFTING_PAGE_SIZE = 5


def _recipe_line(recipe: dict, idx: int, player_level: int) -> str:
    req_level = int(recipe["required_level"])
    icon = "🔓" if player_level >= req_level else "🔒"
    ingredients = " + ".join(f"{name} x{qty}" for name, qty in recipe["ingredients"])
    result_name, result_qty = recipe["result"]
    lock_note = "" if player_level >= req_level else f" (нужен {req_level} ур.)"
    return f"{icon} {idx}. {recipe['name']}{lock_note}\n   {ingredients} -> {result_name} x{result_qty}"


def _inventory_quantities(user_id: int) -> dict[str, int]:
    quantities: dict[str, int] = {}
    for item in database.get_user_inventory(user_id):
        name = str(item.get("name") or "")
        if not name:
            continue
        quantities[name] = quantities.get(name, 0) + int(item.get("quantity", 0) or 0)
    try:
        from game.gacha.service import get_signal_shards
        quantities["Осколки сигнала"] = get_signal_shards(user_id)
    except Exception:
        quantities.setdefault("Осколки сигнала", 0)
    return quantities


def _recipe_status(recipe: dict, craft_level: int, quantities: dict[str, int]) -> dict:
    missing = []
    for name, required_qty in [*recipe.get("ingredients", []), *recipe.get("currency_ingredients", [])]:
        have_qty = int(quantities.get(name, 0) or 0)
        if have_qty < int(required_qty):
            missing.append((name, have_qty, int(required_qty)))
    required_level = int(recipe["required_level"])
    level_ok = craft_level >= required_level
    return {
        "can_craft": level_ok and not missing,
        "level_ok": level_ok,
        "required_level": required_level,
        "missing": missing,
    }


def _split_recipes_by_status(craft_level: int, quantities: dict[str, int]) -> tuple[list[tuple[int, dict, dict]], list[tuple[int, dict, dict]]]:
    available = []
    unavailable = []
    for idx, recipe in enumerate(CRAFT_RECIPES, 1):
        status = _recipe_status(recipe, craft_level, quantities)
        row = (idx, recipe, status)
        if status["can_craft"]:
            available.append(row)
        else:
            unavailable.append(row)
    return available, unavailable


def _crafting_page_bounds(total_items: int, page: int = 0) -> tuple[int, int, int, int]:
    total_pages = max(1, (max(0, int(total_items)) + CRAFTING_PAGE_SIZE - 1) // CRAFTING_PAGE_SIZE)
    safe_page = max(0, min(total_pages - 1, int(page or 0)))
    start = safe_page * CRAFTING_PAGE_SIZE
    return safe_page, total_pages, start, start + CRAFTING_PAGE_SIZE


def _find_recipe_by_id(recipe_id: str) -> dict | None:
    for recipe in CRAFT_RECIPES:
        if recipe.get("id") == recipe_id:
            return recipe
    return None


def _format_recipe_card(idx: int, recipe: dict, status: dict, *, available_view: bool) -> str:
    result_name, result_qty = recipe["result"]
    ingredients = []
    for name, required_qty in [*recipe.get("ingredients", []), *recipe.get("currency_ingredients", [])]:
        ingredients.append(f"{name} x{required_qty}")
    lines = [
        f"{idx}. {recipe['name']}",
        f"   Итог: {result_name} x{result_qty}",
        f"   Нужно: {', '.join(ingredients)}",
    ]
    if recipe.get("description"):
        lines.append(f"   Эффект: {recipe['description']}")
    if available_view:
        lines.append("   Статус: можно крафтить")
    else:
        reasons = []
        if not status["level_ok"]:
            reasons.append(f"навык {status['required_level']}")
        for name, have_qty, required_qty in status["missing"][:3]:
            reasons.append(f"{name} {have_qty}/{required_qty}")
        if len(status["missing"]) > 3:
            reasons.append(f"ещё {len(status['missing']) - 3}")
        lines.append(f"   Не хватает: {', '.join(reasons) if reasons else 'условия рецепта'}")
    return "\n".join(lines)


def _crafting_keyboard(rows: list[tuple[int, dict, dict]], view: str, page: int, total_pages: int):
    safe_view = "blocked" if view == "blocked" else "available"
    keyboard = VkKeyboard(one_time=False, inline=True)
    keyboard.add_callback_button(
        "Можно",
        color=VkKeyboardColor.POSITIVE if safe_view == "available" else VkKeyboardColor.SECONDARY,
        payload={"command": "crafting_page", "view": "available", "page": 0},
    )
    keyboard.add_callback_button(
        "Нельзя",
        color=VkKeyboardColor.PRIMARY if safe_view == "blocked" else VkKeyboardColor.SECONDARY,
        payload={"command": "crafting_page", "view": "blocked", "page": 0},
    )

    keyboard.add_line()
    prev_page = (page - 1) % total_pages
    next_page = (page + 1) % total_pages
    keyboard.add_callback_button(
        "Назад",
        color=VkKeyboardColor.SECONDARY,
        payload={"command": "crafting_page", "view": safe_view, "page": prev_page},
    )
    keyboard.add_callback_button(
        f"{page + 1}/{total_pages}",
        color=VkKeyboardColor.PRIMARY,
        payload={"command": "crafting_page", "view": safe_view, "page": page},
    )
    keyboard.add_callback_button(
        "След.",
        color=VkKeyboardColor.SECONDARY,
        payload={"command": "crafting_page", "view": safe_view, "page": next_page},
    )
    return keyboard


def _send_crafting_screen(vk, user_id: int, message: str, keyboard):
    try_edit_or_send_ui(vk, user_id, "crafting", message, keyboard=keyboard.get_keyboard())


def show_crafting_menu(player, vk, user_id: int, view: str = "available", page: int = 0):
    if player.current_location_id != "убежище":
        vk.messages.send(
            user_id=user_id,
            message="Верстак доступен только в убежище.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    progress = get_crafting_progress(user_id)
    level = int(progress["level"])
    xp = int(progress["xp"])
    next_threshold = int(progress["next_threshold"])
    quantities = _inventory_quantities(user_id)
    available, unavailable = _split_recipes_by_status(level, quantities)
    safe_view = "blocked" if view == "blocked" else "available"
    rows = unavailable if safe_view == "blocked" else available
    safe_page, total_pages, start, end = _crafting_page_bounds(len(rows), page)
    page_rows = rows[start:end]

    if level >= CRAFTING_MAX_LEVEL:
        progress_line = f"Навык крафта: {level}/{CRAFTING_MAX_LEVEL} (максимум)"
    else:
        progress_line = f"Навык крафта: {level}/{CRAFTING_MAX_LEVEL} ({xp}/{next_threshold} XP)"

    section_title = "МОЖНО СКРАФТИТЬ" if safe_view == "available" else "ПОКА НЕЛЬЗЯ СКРАФТИТЬ"
    lines = [
        ui.title("Крафт: верстак"),
        progress_line,
        f"Готово сейчас: {len(available)} | Не хватает условий: {len(unavailable)}",
        "",
        ui.section(section_title),
        f"Страница: {safe_page + 1}/{total_pages}",
    ]
    if page_rows:
        for idx, recipe, status in page_rows:
            lines.append("")
            lines.append(_format_recipe_card(idx, recipe, status, available_view=safe_view == "available"))
    else:
        lines.append("")
        lines.append("В этом списке пока пусто.")

    lines.append("")
    lines.append(ui.section("Управление"))
    lines.append("Страницы и разделы — inline-кнопками. Крафт: скрафтить <номер>.")

    _send_crafting_screen(
        vk,
        user_id,
        "\n".join(lines),
        _crafting_keyboard(page_rows, safe_view, safe_page, total_pages),
    )


def show_workbench_menu(player, vk, user_id: int):
    """Главный экран верстака в убежище."""
    if player.current_location_id != "убежище":
        vk.messages.send(
            user_id=user_id,
            message="Верстак доступен только в убежище.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    lines = [
        "🛠️ ВЕРСТАК УБЕЖИЩА",
        "",
        "• Крафт — рецепты предметов и улучшения снаряжения.",
        "• Улучшение оружия — прокачка ATK материалами опыта и прорывы материалами Склад 17.",
        "",
        "Выбери раздел.",
    ]
    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=create_workbench_keyboard().get_keyboard(),
        random_id=0,
    )


def show_weapon_upgrade_menu(player, vk, user_id: int):
    """Экран прокачки оружия на верстаке."""
    if player.current_location_id != "убежище":
        vk.messages.send(
            user_id=user_id,
            message="Улучшение оружия доступно только через верстак в убежище.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return

    player.inventory.reload()
    materials = database.get_user_weapon_materials(user_id)
    equipped_weapon = next(
        (weapon for weapon in player.inventory.weapons if weapon.get("name") == player.equipped_weapon),
        None,
    )

    lines = [
        "🔧 УЛУЧШЕНИЕ ОРУЖИЯ",
        "",
        "ATK растёт от уровней. Доп. стат ивент-оружия растёт после прорывов.",
        "",
        "Материалы опыта:",
    ]
    for name, xp_value in sorted(WEAPON_XP_MATERIALS.items(), key=lambda row: row[1]):
        lines.append(f"• {name}: x{materials.get(name, 0)} ({xp_value} XP)")

    lines.append("")
    lines.append("Материалы прорыва:")
    for name in sorted(ASCENSION_MATERIALS):
        lines.append(f"• {name}: x{materials.get(name, 0)}")

    lines.append("")
    lines.append("Надетое оружие:")
    if equipped_weapon:
        name = equipped_weapon.get("name", "Оружие")
        level = int(equipped_weapon.get("item_level", 1) or 1)
        cap = int(equipped_weapon.get("weapon_cap", equipped_weapon.get("required_level", 1)) or 1)
        ascension = int(equipped_weapon.get("weapon_ascension", 0) or 0)
        attack = int(equipped_weapon.get("attack", 0) or 0)
        rank = equipped_weapon.get("item_rank", "common")
        lines.append(name)
        lines.append(f"ATK {attack} | L{level}/{cap} | Прорыв {ascension}/10 | Ранг {rank}")
        if equipped_weapon.get("event_bonus_text"):
            lines.append(f"Доп. стат: {equipped_weapon.get('event_bonus_name')}: {equipped_weapon.get('event_bonus_text')}")
    else:
        lines.append("Оружие не надето. Открой инвентарь и надень нужный предмет.")

    lines.append("")
    lines.append("Команды:")
    lines.append("• улучшить оружие — поднять надетое оружие до текущего капа")
    lines.append("• прорыв оружия — открыть следующий диапазон надетого оружия")

    vk.messages.send(
        user_id=user_id,
        message="\n".join(lines),
        keyboard=create_weapon_upgrade_keyboard().get_keyboard(),
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


def craft_recipe(player, vk, user_id: int, target: str, *, refresh_view: str | None = None, refresh_page: int = 0):
    reply_keyboard = None if refresh_view else create_location_keyboard(player.current_location_id, player.level).get_keyboard()
    reply_kwargs = {"keyboard": reply_keyboard} if reply_keyboard else {}
    if player.current_location_id != "убежище":
        vk.messages.send(
            user_id=user_id,
            message="Крафт доступен только в убежище.",
            **reply_kwargs,
            random_id=0,
        )
        return

    recipe = _find_recipe_by_text(target)
    if not recipe:
        vk.messages.send(
            user_id=user_id,
            message="Рецепт не найден. Открой 'Крафт' и выбери номер рецепта.",
            **reply_kwargs,
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
            **reply_kwargs,
            random_id=0,
        )
        return

    result_name, result_qty = recipe["result"]
    if recipe.get("resonance_ticket_banner"):
        from game.gacha.service import convert_signal_shards_to_tickets
        tx = convert_signal_shards_to_tickets(user_id, str(recipe["resonance_ticket_banner"]), int(result_qty))
    else:
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
            **reply_kwargs,
            random_id=0,
        )
        return

    gain = add_crafting_xp(user_id, int(recipe.get("xp_gain", 0) or 0))
    level_up_msg = ""
    if gain["new_level"] > gain["old_level"]:
        level_up_msg = f"\n🎯 Навык крафта повышен: {gain['old_level']} -> {gain['new_level']}"

    ingredients_text = ", ".join(
        f"{name} x{qty}"
        for name, qty in [*recipe.get("ingredients", []), *recipe.get("currency_ingredients", [])]
    )
    vk.messages.send(
        user_id=user_id,
        message=(
            f"✅ Скрафчено: {result_name} x{result_qty}\n"
            f"Списано: {ingredients_text}\n"
            f"Опыт крафта: +{gain['gained']} (всего {gain['new_xp']})"
            f"{level_up_msg}"
        ),
        **reply_kwargs,
        random_id=0,
    )
    if refresh_view:
        show_crafting_menu(player, vk, user_id, view=refresh_view, page=refresh_page)


def handle_crafting_callback(player, vk, user_id: int, payload: dict) -> bool:
    command = payload.get("command")
    if command not in {"crafting_page", "crafting_build"}:
        return False

    view = str(payload.get("view") or "available")
    page = int(payload.get("page", 0) or 0)
    if command == "crafting_page":
        show_crafting_menu(player, vk, user_id, view=view, page=page)
        return True

    recipe_id = str(payload.get("recipe_id") or "")
    recipe = _find_recipe_by_id(recipe_id)
    if not recipe:
        vk.messages.send(user_id=user_id, message="Рецепт устарел. Открой крафт заново.", random_id=0)
        show_crafting_menu(player, vk, user_id, view=view, page=page)
        return True

    craft_recipe(
        player,
        vk,
        user_id,
        recipe["name"],
        refresh_view=view,
        refresh_page=page,
    )
    return True
