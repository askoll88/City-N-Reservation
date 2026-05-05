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
    SSR_HARD_PITY,
)
from .service import get_banners, get_banner_state, get_signal_shards, is_resonance_available, perform_pulls
from .service import get_banner_time_left
from .service import get_pull_history


RARITY_VIEW = {
    "SSR": {"icon": "🟨", "title": "ЛЕГЕНДАРНЫЙ СИГНАЛ"},
    "SR": {"icon": "🟪", "title": "РЕДКИЙ ОТКЛИК"},
    "R": {"icon": "⬜", "title": "СЛАБЫЙ СИГНАЛ"},
}

HISTORY_PAGE_SIZE = 5


def _add_callback_button(keyboard: VkKeyboard, label: str, *, command: str, color=VkKeyboardColor.SECONDARY, **payload) -> None:
    keyboard.add_callback_button(label, color=color, payload={"command": command, **payload})


def create_resonance_keyboard() -> VkKeyboard:
    keyboard = VkKeyboard(one_time=False, inline=True)
    _add_callback_button(keyboard, "Резонанс оружия", command="resonance_banner", banner="weapon", color=VkKeyboardColor.PRIMARY)
    _add_callback_button(keyboard, "Резонанс снаряжения", command="resonance_banner", banner="outfit", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "Шансы оружия", command="resonance_rates", banner="weapon", color=VkKeyboardColor.SECONDARY)
    _add_callback_button(keyboard, "Шансы снаряжения", command="resonance_rates", banner="outfit", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "История резонанса", command="resonance_history_index", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "Назад", command="resonance_exit", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_resonance_banner_keyboard(banner_id: str) -> VkKeyboard:
    keyboard = VkKeyboard(one_time=False, inline=True)
    _add_callback_button(keyboard, "x1", command="resonance_pull", banner=banner_id, count=1, color=VkKeyboardColor.PRIMARY)
    _add_callback_button(keyboard, "x10", command="resonance_pull", banner=banner_id, count=10, color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    _add_callback_button(keyboard, "Шансы", command="resonance_rates", banner=banner_id, color=VkKeyboardColor.SECONDARY)
    _add_callback_button(keyboard, "История", command="resonance_history", banner=banner_id, page=0, color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "Назад к резонансу", command="resonance_back", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_resonance_rates_keyboard() -> VkKeyboard:
    keyboard = VkKeyboard(one_time=False, inline=True)
    _add_callback_button(keyboard, "Шансы оружия", command="resonance_rates", banner="weapon", color=VkKeyboardColor.SECONDARY)
    _add_callback_button(keyboard, "Шансы снаряжения", command="resonance_rates", banner="outfit", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    _add_callback_button(keyboard, "Назад к резонансу", command="resonance_back", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def create_resonance_history_index_keyboard() -> VkKeyboard:
    keyboard = VkKeyboard(one_time=False, inline=True)
    _add_callback_button(keyboard, "История оружия", command="resonance_history", banner="weapon", page=0, color=VkKeyboardColor.PRIMARY)
    _add_callback_button(keyboard, "История снаряжения", command="resonance_history", banner="outfit", page=0, color=VkKeyboardColor.PRIMARY)
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
        "История резонанса — последние отклики по баннерам",
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


def format_rates(banner_id: str | None = None) -> str:
    banner = next((item for item in get_banners() if item.id == banner_id), None) if banner_id else None
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


def format_history_index() -> str:
    return (
        "▰ ИСТОРИЯ РЕЗОНАНСА\n\n"
        "История разделена по баннерам, потому что пити и гарант считаются отдельно.\n\n"
        "Выбери, какой журнал открыть."
    )


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
            "Резонанс Зоны пока закрыт: система включается админом и доступна только администраторам для тестов.",
            create_location_keyboard(player.current_location_id, player.level),
        )
        return
    _show_hud(vk, user_id, format_resonance_menu(user_id), create_resonance_keyboard(), screen="menu")


def show_banner_menu(vk, user_id: int, banner_id: str) -> None:
    _show_hud(vk, user_id, format_banner_menu(user_id, banner_id), create_resonance_banner_keyboard(banner_id), screen=f"banner:{banner_id}")


def show_rates(vk, user_id: int, banner_id: str | None = None) -> None:
    _show_hud(vk, user_id, format_rates(banner_id), create_resonance_rates_keyboard(), screen=f"rates:{banner_id or 'all'}")


def show_history_index(vk, user_id: int) -> None:
    _show_hud(vk, user_id, format_history_index(), create_resonance_history_index_keyboard(), screen="history:index")


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
    if text in {"история резонанса", "история откликов"}:
        if not _can_use_resonance_text(player, vk, user_id):
            return True
        show_history_index(vk, user_id)
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
        show_rates(vk, user_id, banner_id)
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
        show_rates(vk, user_id, str(payload.get("banner") or "") or None)
        return True
    if command == "resonance_history_index":
        show_history_index(vk, user_id)
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
