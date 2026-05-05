"""Player-facing UI for Resonance Zone."""

from __future__ import annotations

from vk_api.keyboard import VkKeyboard, VkKeyboardColor

from handlers.keyboards import create_location_keyboard
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


RARITY_VIEW = {
    "SSR": {"icon": "🟨", "title": "ЛЕГЕНДАРНЫЙ СИГНАЛ"},
    "SR": {"icon": "🟪", "title": "РЕДКИЙ ОТКЛИК"},
    "R": {"icon": "⬜", "title": "СЛАБЫЙ СИГНАЛ"},
}


def create_resonance_keyboard() -> VkKeyboard:
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Оружие x1", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Оружие x10", color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button("Снаряжение x1", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Снаряжение x10", color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button("Резонанс Зоны", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Шансы Резонанса", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Назад", color=VkKeyboardColor.NEGATIVE)
    return keyboard


def _send(vk, user_id: int, message: str, keyboard=None, attachment: str | None = None) -> None:
    if keyboard is None:
        keyboard = create_resonance_keyboard()
    vk_messages.send(vk, user_id=user_id, message=message, keyboard=keyboard, attachment=attachment)


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
    lines = [
        "▰ РЕЗОНАНС ЗОНЫ",
        "Приёмник ловит обрывки сигнала. Выбери, куда направить отклик.",
        "",
        "• РЕСУРС",
        f"💠 Осколки сигнала: {get_signal_shards(vk_id)}",
        f"Отклик x1: {SINGLE_PULL_COST} | Отклик x10: {TEN_PULL_COST}",
        f"Цикл баннера: {BANNER_DURATION_DAYS} дней",
        "",
        "• БАННЕРЫ",
    ]
    for banner in get_banners():
        state = get_banner_state(vk_id, banner.id)
        guarantee = "rate-up гарантирован" if state.get("featured_guaranteed") else "50/50 активен"
        lines.extend([
            "",
            f"◆ {banner.name.upper()}",
            f"Rate-up SSR: {_featured_line(banner.featured_ssr)}",
            f"SSR {_bar(state['pity_ssr'], SSR_HARD_PITY)} {state['pity_ssr']}/{SSR_HARD_PITY}",
            f"SR  {_bar(state['pity_sr'], SR_HARD_PITY)} {state['pity_sr']}/{SR_HARD_PITY}",
            f"Гарант: {guarantee}",
        ])
    lines.extend([
        "",
        "• ДЕЙСТВИЯ",
        "Оружие x1/x10 — оружейный баннер",
        "Снаряжение x1/x10 — баннер комплекта",
    ])
    return "\n".join(lines)


def format_rates() -> str:
    return (
        "▰ ПРАВИЛА РЕЗОНАНСА\n\n"
        "• ШАНСЫ\n"
        "🟨 SSR: 1.6% базово. После 65 откликов сигнал усиливается. На 80 — гарант.\n"
        "🟪 SR: 12% базово. На 10 отклике — гарант.\n"
        "⬜ R: расходники, гильзы и материалы для тестовой экономики.\n\n"
        "• RATE-UP\n"
        "Первый SSR проходит через 50/50. Если rate-up не выпал, следующий SSR "
        "на этом типе баннера будет гарантированно rate-up.\n\n"
        "• ПИТИ\n"
        "Оружие и снаряжение считают пити отдельно. Переключение баннера не сбрасывает прогресс."
    )


def _format_pull_result(result: dict) -> str:
    rewards = result["rewards"]
    best_rarity = "SSR" if any(r.rarity == "SSR" for r in rewards) else "SR" if any(r.rarity == "SR" for r in rewards) else "R"
    best_title = RARITY_VIEW[best_rarity]["title"]
    lines = [
        f"▰ {best_title}",
        f"{result['banner'].name} | Откликов: x{result['count']}",
        f"Потрачено: {result['cost']} осколков | Осталось: {result['shards_left']}",
        "",
        "• РАСШИФРОВКА СИГНАЛА",
    ]
    for idx, reward in enumerate(rewards, 1):
        suffix = " (дубликат)" if reward.duplicate else ""
        qty = f" x{reward.quantity}" if reward.quantity != 1 else ""
        lines.append(f"{idx}. {_rarity_icon(reward.rarity)} {reward.rarity} — {reward.name}{qty}{suffix}")
    state = result["state"]
    guarantee = "следующий SSR гарантированно rate-up" if state.get("featured_guaranteed") else "50/50 активен"
    lines.extend([
        "",
        "• СОСТОЯНИЕ БАННЕРА",
        f"SSR {_bar(state['pity_ssr'], SSR_HARD_PITY)} {state['pity_ssr']}/{SSR_HARD_PITY}",
        f"SR  {_bar(state['pity_sr'], SR_HARD_PITY)} {state['pity_sr']}/{SR_HARD_PITY}",
        f"Гарант: {guarantee}",
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
    _send(vk, user_id, format_resonance_menu(user_id), create_resonance_keyboard())


def handle_resonance_command(player, vk, user_id: int, text: str) -> bool:
    text = (text or "").strip().lower()
    if text in {"резонанс", "резонанс зоны", "резонанс зоны", "отклик", "отклики"}:
        show_resonance_menu(player, vk, user_id)
        return True
    if text in {"шансы резонанса", "шансы резонанс"}:
        if not is_resonance_available(user_id):
            show_resonance_menu(player, vk, user_id)
            return True
        _send(vk, user_id, format_rates(), create_resonance_keyboard())
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
    _send(vk, user_id, message, create_resonance_keyboard(), attachment=attachment)
    return True
