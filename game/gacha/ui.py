"""Player-facing UI for Resonance Zone."""

from __future__ import annotations

from vk_api.keyboard import VkKeyboard, VkKeyboardColor

from handlers.keyboards import create_location_keyboard
from infra.state_manager import get_ui_current_screen, set_ui_screen, try_edit_or_send_ui
from infra import vk_messages

from .assets import first_ssr_attachment
from .banners import (
    BANNER_DURATION_DAYS,
    SINGLE_PULL_COST,
    TEN_PULL_COST,
    SR_HARD_PITY,
    SR_BASE_RATE,
    SSR_HARD_PITY,
    SSR_BASE_RATE,
    SSR_SOFT_PITY_START,
    SSR_SOFT_PITY_STEP,
)
from .service import get_banners, get_banner_state, get_signal_shards, is_resonance_available, perform_pulls
from .service import get_banner_time_left
from .service import get_pull_history
from .event_items import (
    GACHA_EVENT_ITEMS,
    format_event_outfit_passive_stats,
    get_event_item_lore,
    get_event_outfit_passive_profile,
    get_event_weapon_stat_profile,
)


RARITY_VIEW = {
    "SSR": {"icon": "🟨", "title": "ЛЕГЕНДАРНЫЙ СИГНАЛ"},
    "SR": {"icon": "🟪", "title": "РЕДКИЙ ОТКЛИК"},
    "R": {"icon": "⬜", "title": "СЛАБЫЙ СИГНАЛ"},
}

HISTORY_PAGE_SIZE = 5
RATES_TOTAL_PAGES = 3
_EVENT_ITEMS_BY_NAME = {row[0]: row for row in GACHA_EVENT_ITEMS}


def _add_callback_button(keyboard: VkKeyboard, label: str, *, command: str, color=VkKeyboardColor.SECONDARY, **payload) -> None:
    keyboard.add_callback_button(label, color=color, payload={"command": command, **payload})


def create_resonance_keyboard() -> VkKeyboard:
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Резонанс оружия", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Резонанс снаряжения", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Шансы оружия", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Шансы снаряжения", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_resonance_banner_keyboard(banner_id: str) -> VkKeyboard:
    prefix = "Оружие" if banner_id == "weapon" else "Снаряжение"
    history_label = "История оружия" if banner_id == "weapon" else "История снаряжения"
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button(f"{prefix} x1", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button(f"{prefix} x10", color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button(history_label, color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад к резонансу", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_resonance_rates_keyboard(banner_id: str, page: int = 0, total_pages: int = RATES_TOTAL_PAGES) -> VkKeyboard:
    total = max(1, int(total_pages or 1))
    current = max(0, min(total - 1, int(page or 0)))
    keyboard = VkKeyboard(one_time=False, inline=True)
    _add_callback_button(
        keyboard,
        "Назад",
        command="resonance_rates",
        banner=banner_id,
        page=(current - 1) % total,
        color=VkKeyboardColor.SECONDARY,
    )
    _add_callback_button(
        keyboard,
        f"{current + 1}/{total}",
        command="resonance_rates",
        banner=banner_id,
        page=current,
        color=VkKeyboardColor.PRIMARY,
    )
    _add_callback_button(
        keyboard,
        "След.",
        command="resonance_rates",
        banner=banner_id,
        page=(current + 1) % total,
        color=VkKeyboardColor.SECONDARY,
    )
    keyboard.add_line()
    _add_callback_button(keyboard, "Назад к резонансу", command="resonance_back", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_resonance_history_keyboard(banner_id: str, page: int = 0, total_pages: int = 1) -> VkKeyboard:
    total = max(1, int(total_pages or 1))
    current = max(0, min(total - 1, int(page or 0)))
    keyboard = VkKeyboard(one_time=False, inline=True)
    _add_callback_button(
        keyboard,
        "Назад",
        command="resonance_history",
        banner=banner_id,
        page=(current - 1) % total,
        color=VkKeyboardColor.SECONDARY,
    )
    _add_callback_button(
        keyboard,
        f"{current + 1}/{total}",
        command="resonance_history",
        banner=banner_id,
        page=current,
        color=VkKeyboardColor.PRIMARY,
    )
    _add_callback_button(
        keyboard,
        "След.",
        command="resonance_history",
        banner=banner_id,
        page=(current + 1) % total,
        color=VkKeyboardColor.SECONDARY,
    )
    keyboard.add_line()
    _add_callback_button(keyboard, "Назад к резонансу", command="resonance_back", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def _send(vk, user_id: int, message: str, keyboard=None, attachment: str | None = None) -> None:
    if keyboard is None:
        keyboard = create_resonance_keyboard()
    vk_messages.send(vk, user_id=user_id, message=message, keyboard=keyboard, attachment=attachment)


def _show_hud(vk, user_id: int, message: str, keyboard=None, *, screen: str = "resonance") -> None:
    current_ui = get_ui_current_screen(user_id)
    push_current = current_ui.get("name") != "resonance"
    set_ui_screen(user_id, {"name": "resonance", "screen": screen}, push_current=push_current)
    try_edit_or_send_ui(vk, user_id, "resonance", message, keyboard=(keyboard or create_resonance_keyboard()).get_keyboard())


def _bar(current: int, total: int, width: int = 12) -> str:
    total = max(1, int(total or 1))
    current = max(0, min(int(current or 0), total))
    filled = min(width, int(round(width * current / total)))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _rarity_icon(rarity: str) -> str:
    return RARITY_VIEW.get(rarity, RARITY_VIEW["R"])["icon"]


def _featured_line(items: tuple[str, ...]) -> str:
    if not items:
        return "-"
    if len(items) == 1:
        return items[0]
    return ", ".join(items)


def format_resonance_menu(vk_id: int) -> str:
    time_left = get_banner_time_left()
    lines = [
        "▰ РЕЗОНАНС ЗОНЫ",
        "Приёмник ловит обрывки сигнала. Выбери баннер или посмотри шансы.",
        "",
        "• РЕСУРС",
        f"💠 Осколки сигнала: {get_signal_shards(vk_id)}",
        f"Отклик x1: {SINGLE_PULL_COST} | Отклик x10: {TEN_PULL_COST}",
        f"Цикл баннера: {BANNER_DURATION_DAYS} дней",
        f"До конца баннера: {time_left['formatted']}",
        "",
        "• БАННЕРЫ",
    ]
    for banner in get_banners():
        state = get_banner_state(vk_id, banner.id)
        guarantee = "rate-up гарантирован" if state.get("featured_guaranteed") else "50/50 активен"
        lines.extend([
            "",
            f"◆ {banner.name.upper()}",
            f"До конца: {time_left['formatted']}",
            f"Rate-up SSR: {_featured_line(banner.featured_ssr)}",
            f"SSR {_bar(state['pity_ssr'], SSR_HARD_PITY)} {state['pity_ssr']}/{SSR_HARD_PITY}",
            f"SR  {_bar(state['pity_sr'], SR_HARD_PITY)} {state['pity_sr']}/{SR_HARD_PITY}",
            f"Гарант: {guarantee}",
        ])
    lines.extend([
        "",
        "• ДЕЙСТВИЯ",
        "Резонанс оружия — к оружейному баннеру",
        "Резонанс снаряжения — к баннеру комплекта",
    ])
    return "\n".join(lines)


def format_banner_menu(vk_id: int, banner_id: str) -> str:
    banner = next((item for item in get_banners() if item.id == banner_id), None)
    if not banner:
        return "Неизвестный баннер Резонанса."
    state = get_banner_state(vk_id, banner.id)
    time_left = get_banner_time_left()
    guarantee = "rate-up гарантирован" if state.get("featured_guaranteed") else "50/50 активен"
    lines = [
        f"▰ {banner.name.upper()}",
        f"До конца баннера: {time_left['formatted']}",
        "",
        "• РЕСУРС",
        f"💠 Осколки сигнала: {get_signal_shards(vk_id)}",
        f"x1: {SINGLE_PULL_COST} | x10: {TEN_PULL_COST}",
        "",
        "• RATE-UP",
        f"SSR: {_featured_line(banner.featured_ssr)}",
        f"Off-rate SSR: {_featured_line(banner.off_ssr)}",
        "",
        "• ПРОГРЕСС",
        f"SSR {_bar(state['pity_ssr'], SSR_HARD_PITY)} {state['pity_ssr']}/{SSR_HARD_PITY}",
        f"SR  {_bar(state['pity_sr'], SR_HARD_PITY)} {state['pity_sr']}/{SR_HARD_PITY}",
        f"Гарант: {guarantee}",
    ]
    return "\n".join(lines)


def _get_banner_by_id(banner_id: str | None):
    return next((item for item in get_banners() if item.id == banner_id), None)


def _item_template(item_name: str) -> dict:
    row = _EVENT_ITEMS_BY_NAME.get(str(item_name or "").strip())
    if not row:
        return {"name": item_name or "Предмет", "category": "item", "attack": 0, "defense": 0, "weight": 0, "rarity": "-"}
    return {
        "name": row[0],
        "category": row[1],
        "description": row[2],
        "price": row[3],
        "attack": row[4],
        "defense": row[5],
        "weight": row[6],
        "rarity": row[8] if len(row) >= 9 else "common",
    }


def _format_item_stats(item_name: str) -> list[str]:
    item = _item_template(item_name)
    lines = []
    if int(item.get("attack", 0) or 0) > 0:
        lines.append(f"АТК: {int(item['attack'])}")
    if int(item.get("defense", 0) or 0) > 0:
        lines.append(f"Защита: {int(item['defense'])}")
    if float(item.get("weight", 0) or 0) > 0:
        lines.append(f"Вес: {float(item['weight']):g}кг")

    weapon_profile = get_event_weapon_stat_profile(item_name)
    if weapon_profile:
        try:
            from game.weapon_progression import EVENT_WEAPON_STAT_LABELS
        except Exception:
            EVENT_WEAPON_STAT_LABELS = {}
        stat_parts = []
        for stat_name, bounds in (weapon_profile.get("stats") or {}).items():
            label = EVENT_WEAPON_STAT_LABELS.get(stat_name, stat_name)
            suffix = "" if stat_name == "bleed_damage" else "%"
            if isinstance(bounds, tuple):
                stat_parts.append(f"{label}: +{bounds[0]}{suffix} -> +{bounds[1]}{suffix}")
            else:
                stat_parts.append(f"{label}: +{bounds}{suffix}")
        stat_text = ", ".join(stat_parts)
        if stat_text:
            lines.append(f"{weapon_profile['name']}: {stat_text}")
        if weapon_profile.get("description"):
            lines.append(weapon_profile["description"])

    outfit_profile = get_event_outfit_passive_profile(item_name)
    if outfit_profile:
        stats = format_event_outfit_passive_stats(outfit_profile.get("stats"))
        if stats:
            lines.append(f"{outfit_profile['name']}: {stats}")
        if outfit_profile.get("description"):
            lines.append(outfit_profile["description"])
    return lines


def _format_item_presentation(item_name: str, *, prefix: str = "") -> list[str]:
    item = _item_template(item_name)
    title = f"{prefix}{item['name']}" if prefix else item["name"]
    lines = [f"◆ {title}"]
    stat_lines = _format_item_stats(item_name)
    if stat_lines:
        lines.extend([f"  {line}" for line in stat_lines])
    lore = get_event_item_lore(item_name) or str(item.get("description") or "")
    if lore:
        lines.append(f"  {lore}")
    return lines


def _format_rate_value(percent: float) -> str:
    return f"{percent:.3f}".rstrip("0").rstrip(".") + "%"


def _format_rateup_rates(banner) -> list[str]:
    featured_count = max(1, len(banner.featured_ssr or ()))
    per_featured = (SSR_BASE_RATE * 0.5) / featured_count
    guaranteed_per_featured = SSR_BASE_RATE / featured_count
    return [
        f"SSR базово: {_format_rate_value(SSR_BASE_RATE)}",
        f"Rate-up при активном 50/50: {_format_rate_value(per_featured)} на предмет",
        f"Rate-up после проигрыша 50/50: {_format_rate_value(guaranteed_per_featured)} на предмет SSR-проверки",
    ]


def _format_offrate_rates(banner) -> list[str]:
    off_count = max(1, len(banner.off_ssr or banner.featured_ssr or ()))
    per_off = (SSR_BASE_RATE * 0.5) / off_count
    return [
        f"Проигрыш 50/50: 50% от SSR-срабатывания",
        f"Базово на каждый предмет пула: {_format_rate_value(per_off)}",
    ]


def _format_rates_rateup_page(banner, page: int) -> str:
    lines = [
        f"▰ ШАНСЫ: {banner.name.upper()}",
        f"Страница {page + 1}/{RATES_TOTAL_PAGES}: rate-up SSR",
        "",
        "• ГЛАВНЫЙ СИГНАЛ БАННЕРА",
    ]
    for item_name in banner.featured_ssr:
        lines.extend(_format_item_presentation(item_name, prefix="RankUP SSR: "))
        lines.append("")
    lines.extend(["• ШАНС ПОЛУЧЕНИЯ", *_format_rateup_rates(banner)])
    return "\n".join(line for line in lines if line is not None).rstrip()


def _format_rates_offrate_page(banner, page: int) -> str:
    lines = [
        f"▰ ШАНСЫ: {banner.name.upper()}",
        f"Страница {page + 1}/{RATES_TOTAL_PAGES}: проигрыш 50/50",
        "",
        "• ПУЛ OFF-RATE SSR",
    ]
    if not banner.off_ssr:
        lines.append("Off-rate пул пуст. При проигрыше используется rate-up пул.")
    else:
        for item_name in banner.off_ssr:
            lines.extend(_format_item_presentation(item_name))
            lines.append("")
    lines.extend(["• ШАНС ПУЛА", *_format_offrate_rates(banner)])
    return "\n".join(line for line in lines if line is not None).rstrip()


def _format_rates_details_page(banner, page: int) -> str:
    sr_names = tuple(item.name for item in banner.sr_pool)
    r_names = tuple(item.name for item in banner.r_pool)
    lines = [
        f"▰ ШАНСЫ: {banner.name.upper()}",
        f"Страница {page + 1}/{RATES_TOTAL_PAGES}: подробности",
        "",
        "• БАЗОВЫЕ ШАНСЫ",
        f"🟨 SSR: {_format_rate_value(SSR_BASE_RATE)}. После {SSR_SOFT_PITY_START} откликов шанс растёт на {_format_rate_value(SSR_SOFT_PITY_STEP)} за отклик. На {SSR_HARD_PITY} — гарант.",
        f"🟪 SR: {_format_rate_value(SR_BASE_RATE)}. На {SR_HARD_PITY} отклике — гарант.",
        "⬜ R: всё остальное.",
        "",
        "• ГАРАНТ",
        "Если SSR не оказался rate-up, следующий SSR на этом типе баннера будет rate-up.",
        "Оружие и снаряжение считают пити отдельно.",
        "",
        "• SR ПУЛ",
        _featured_line(sr_names),
        "",
        "• R ПУЛ",
        _featured_line(r_names),
    ]
    return "\n".join(lines)


def format_rates(banner_id: str | None = None, page: int = 0) -> tuple[str, int, int]:
    banner = _get_banner_by_id(banner_id) if banner_id else None
    if not banner:
        banner = _get_banner_by_id("weapon")
    if not banner:
        return "Неизвестный баннер Резонанса.", 0, 1
    safe_page = max(0, min(RATES_TOTAL_PAGES - 1, int(page or 0)))
    if safe_page == 0:
        message = _format_rates_rateup_page(banner, safe_page)
    elif safe_page == 1:
        message = _format_rates_offrate_page(banner, safe_page)
    else:
        message = _format_rates_details_page(banner, safe_page)
    return message, safe_page, RATES_TOTAL_PAGES


def format_rates_text(banner_id: str | None = None, page: int = 0) -> str:
    message, _safe_page, _total_pages = format_rates(banner_id, page)
    return message


def _legacy_format_rates(banner_id: str | None = None) -> str:
    banner = _get_banner_by_id(banner_id) if banner_id else None
    lines = [
        "▰ ПРАВИЛА РЕЗОНАНСА",
        "",
        "• ШАНСЫ",
        "🟨 SSR: 1.6% базово. После 65 откликов сигнал усиливается. На 80 — гарант.",
        "🟪 SR: 12% базово. На 10 отклике — гарант.",
        "⬜ R: расходники и материалы для тестовой экономики.",
        "",
        "• RATE-UP",
        "Первый SSR проходит через 50/50. Если rate-up не выпал, следующий SSR на этом типе баннера будет гарантированно rate-up.",
        "",
        "• ПИТИ",
        "Оружие и снаряжение считают пити отдельно. Переключение баннера не сбрасывает прогресс.",
    ]
    if banner:
        lines.extend([
            "",
            f"• ПУЛ: {banner.name.upper()}",
            f"Rate-up SSR: {_featured_line(banner.featured_ssr)}",
            f"Off-rate SSR: {_featured_line(banner.off_ssr)}",
            f"SR: {_featured_line(tuple(item.name for item in banner.sr_pool))}",
            f"R: {_featured_line(tuple(item.name for item in banner.r_pool))}",
        ])
    return "\n".join(lines)


def _format_history_ts(ts: int) -> str:
    from datetime import datetime

    if not ts:
        return "-"
    return datetime.fromtimestamp(int(ts)).strftime("%d.%m %H:%M")


def format_history(vk_id: int, banner_id: str, page: int = 0) -> tuple[str, int, int]:
    data = get_pull_history(vk_id, banner_id, page=page, page_size=HISTORY_PAGE_SIZE)
    banner = data.get("banner")
    title = banner.name if banner else "Резонанс"
    safe_page = int(data.get("page", 0) or 0)
    total_pages = int(data.get("total_pages", 1) or 1)
    lines = [
        f"▰ ИСТОРИЯ: {title.upper()}",
        f"Страница: {safe_page + 1}/{total_pages}",
        f"Записей: {int(data.get('total', 0) or 0)}",
        "",
    ]
    items = data.get("items") or []
    if not items:
        lines.append("История пуста. Сделай отклик на этом баннере, и запись появится здесь.")
    else:
        for idx, row in enumerate(items, safe_page * HISTORY_PAGE_SIZE + 1):
            rewards = row.get("rewards") or []
            preview = []
            for reward in rewards[:3]:
                qty = f" x{int(reward.get('quantity', 1) or 1)}" if int(reward.get("quantity", 1) or 1) != 1 else ""
                duplicate = " дубликат" if reward.get("duplicate") else ""
                preview.append(f"{reward.get('rarity', 'R')} {reward.get('name', 'Предмет')}{qty}{duplicate}")
            if len(rewards) > 3:
                preview.append(f"ещё {len(rewards) - 3}")
            lines.extend([
                f"{idx}. {_format_history_ts(int(row.get('ts', 0) or 0))} | x{int(row.get('count', 1) or 1)} | лучшее {row.get('best_rarity', 'R')}",
                f"   {', '.join(preview) if preview else '-'}",
            ])
    return "\n".join(lines), safe_page, total_pages


def _format_pull_result(result: dict) -> str:
    rewards = result["rewards"]
    best_rarity = "SSR" if any(r.rarity == "SSR" for r in rewards) else "SR" if any(r.rarity == "SR" for r in rewards) else "R"
    best_title = RARITY_VIEW[best_rarity]["title"]
    lines = [
        f"▰ {best_title}",
        f"{result['banner'].name} | Откликов: x{result['count']}",
        f"Потрачено: {result['cost']} осколков | Осталось: {result['shards_left']}",
        "Предметы отправлены в шкаф убежища. Дубли SSR конвертируются в осколки.",
        "",
        "• РАСШИФРОВКА СИГНАЛА",
    ]
    for idx, reward in enumerate(rewards, 1):
        if reward.duplicate and reward.kind == "currency":
            source = reward.source_name or "SSR предмет"
            lines.append(
                f"{idx}. {_rarity_icon(reward.rarity)} {reward.rarity} — {source} "
                f"(дубликат -> +{reward.quantity} осколков сигнала)"
            )
            continue
        suffix = " (дубликат)" if reward.duplicate else ""
        qty = f" x{reward.quantity}" if reward.quantity != 1 else ""
        lines.append(f"{idx}. {_rarity_icon(reward.rarity)} {reward.rarity} — {reward.name}{qty}{suffix}")
    state = result["state"]
    time_left = get_banner_time_left()
    guarantee = "следующий SSR гарантированно rate-up" if state.get("featured_guaranteed") else "50/50 активен"
    lines.extend([
        "",
        "• СОСТОЯНИЕ БАННЕРА",
        f"SSR {_bar(state['pity_ssr'], SSR_HARD_PITY)} {state['pity_ssr']}/{SSR_HARD_PITY}",
        f"SR  {_bar(state['pity_sr'], SR_HARD_PITY)} {state['pity_sr']}/{SR_HARD_PITY}",
        f"Гарант: {guarantee}",
        f"До конца баннера: {time_left['formatted']}",
    ])
    return "\n".join(lines)


def show_resonance_menu(player, vk, user_id: int) -> None:
    if player.current_location_id != "убежище":
        _send(
            vk,
            user_id,
            "Резонанс Зоны доступен в убежище.",
            create_location_keyboard(player.current_location_id, player.level),
        )
        return
    if not is_resonance_available(user_id):
        _send(
            vk,
            user_id,
            "Резонанс Зоны пока не отвечает. Вернись позже.",
            create_location_keyboard(player.current_location_id, player.level),
        )
        return
    _show_hud(vk, user_id, format_resonance_menu(user_id), create_resonance_keyboard(), screen="menu")


def show_banner_menu(vk, user_id: int, banner_id: str) -> None:
    _show_hud(vk, user_id, format_banner_menu(user_id, banner_id), create_resonance_banner_keyboard(banner_id), screen=f"banner:{banner_id}")


def show_rates(vk, user_id: int, banner_id: str | None = None, page: int = 0) -> None:
    safe_banner_id = banner_id or "weapon"
    message, safe_page, total_pages = format_rates(safe_banner_id, page)
    _show_hud(
        vk,
        user_id,
        message,
        create_resonance_rates_keyboard(safe_banner_id, safe_page, total_pages),
        screen=f"rates:{safe_banner_id}:{safe_page}",
    )


def show_history(vk, user_id: int, banner_id: str, page: int = 0) -> None:
    message, safe_page, total_pages = format_history(user_id, banner_id, page)
    _show_hud(
        vk,
        user_id,
        message,
        create_resonance_history_keyboard(banner_id, safe_page, total_pages),
        screen=f"history:{banner_id}:{safe_page}",
    )


def handle_resonance_command(player, vk, user_id: int, text: str) -> bool:
    text = (text or "").strip().lower()
    if text in {"резонанс", "резонанс зоны", "резонанс зоны", "отклик", "отклики"}:
        show_resonance_menu(player, vk, user_id)
        return True
    if text in {"резонанс оружия", "оружейный резонанс"}:
        if not _can_use_resonance_text(player, vk, user_id):
            return True
        show_banner_menu(vk, user_id, "weapon")
        return True
    if text in {"резонанс снаряжения"}:
        if not _can_use_resonance_text(player, vk, user_id):
            return True
        show_banner_menu(vk, user_id, "outfit")
        return True
    if text in {"история оружия", "история оружейного резонанса"}:
        if not _can_use_resonance_text(player, vk, user_id):
            return True
        show_history(vk, user_id, "weapon", 0)
        return True
    if text in {"история снаряжения"}:
        if not _can_use_resonance_text(player, vk, user_id):
            return True
        show_history(vk, user_id, "outfit", 0)
        return True
    if text in {"шансы резонанса", "шансы резонанс", "шансы оружия", "шансы снаряжения"}:
        if not is_resonance_available(user_id):
            show_resonance_menu(player, vk, user_id)
            return True
        banner_id = "weapon" if "оруж" in text else "outfit" if "снаряж" in text else None
        show_rates(vk, user_id, banner_id, 0)
        return True

    mapping = {
        "оружие x1": ("weapon", 1),
        "оружие х1": ("weapon", 1),
        "оружейный резонанс x1": ("weapon", 1),
        "оружие x10": ("weapon", 10),
        "оружие х10": ("weapon", 10),
        "оружейный резонанс x10": ("weapon", 10),
        "снаряжение x1": ("outfit", 1),
        "снаряжение х1": ("outfit", 1),
        "резонанс снаряжения x1": ("outfit", 1),
        "снаряжение x10": ("outfit", 10),
        "снаряжение х10": ("outfit", 10),
        "резонанс снаряжения x10": ("outfit", 10),
    }
    target = mapping.get(text)
    if not target:
        return False
    if player.current_location_id != "убежище":
        _send(
            vk,
            user_id,
            "Резонанс Зоны доступен в убежище.",
            create_location_keyboard(player.current_location_id, player.level),
        )
        return True
    banner_id, count = target
    result = perform_pulls(user_id, banner_id, count)
    message = _format_pull_result(result) if result.get("success") else result.get("message", "Не удалось выполнить отклик.")
    attachment = first_ssr_attachment(vk, user_id, result.get("rewards", [])) if result.get("success") else None
    _send(vk, user_id, message, create_resonance_banner_keyboard(banner_id), attachment=attachment)
    return True


def _can_use_resonance_text(player, vk, user_id: int) -> bool:
    if player.current_location_id != "убежище":
        _send(vk, user_id, "Резонанс Зоны доступен в убежище.", create_location_keyboard(player.current_location_id, player.level))
        return False
    if not is_resonance_available(user_id):
        show_resonance_menu(player, vk, user_id)
        return False
    return True


def handle_resonance_callback(player, vk, user_id: int, payload: dict) -> bool:
    command = payload.get("command")
    if command == "resonance_back":
        show_resonance_menu(player, vk, user_id)
        return True
    if command == "resonance_banner":
        show_banner_menu(vk, user_id, str(payload.get("banner") or "weapon"))
        return True
    if command == "resonance_rates":
        show_rates(
            vk,
            user_id,
            str(payload.get("banner") or "weapon"),
            int(payload.get("page", 0) or 0),
        )
        return True
    if command == "resonance_history":
        show_history(
            vk,
            user_id,
            str(payload.get("banner") or "weapon"),
            int(payload.get("page", 0) or 0),
        )
        return True
    if command == "resonance_pull":
        banner_id = str(payload.get("banner") or "weapon")
        count = int(payload.get("count", 1) or 1)
        result = perform_pulls(user_id, banner_id, count)
        message = _format_pull_result(result) if result.get("success") else result.get("message", "Не удалось выполнить отклик.")
        attachment = first_ssr_attachment(vk, user_id, result.get("rewards", [])) if result.get("success") else None
        _send(vk, user_id, message, create_resonance_banner_keyboard(banner_id), attachment=attachment)
        return True
    return False
