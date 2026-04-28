from __future__ import annotations
"""
Обработчики случайных событий
"""
from infra import database
from game.random_events import apply_event_choice, format_event_message
from infra.state_manager import get_pending_event, set_pending_event, clear_pending_event
from infra.state_manager import try_edit_or_send_ui
from handlers.keyboards import create_random_event_keyboard, create_resume_keyboard
from game.emission import handle_emission_warning_response


def show_random_event(player, vk, user_id: int, event: dict, *, prefix: str = ""):
    """Показать активное случайное событие как редактируемый inline-экран."""
    stage_index = int(event.get("_stage_index", 0) or 0)
    message = format_event_message(event, stage_index)
    if prefix:
        message = f"{prefix}\n\n{message}"
    keyboard = create_random_event_keyboard(event, stage_index=stage_index, inline=True).get_keyboard()
    try_edit_or_send_ui(vk, user_id, "random_event", message, keyboard=keyboard)


def handle_event_response(player, vk, user_id: int, text: str) -> bool:
    """Обработка ответа на случайное событие"""

    # Сначала проверяем выброс (приоритет над обычными событиями)
    if handle_emission_warning_response(player, vk, user_id, text):
        return True

    event = get_pending_event(user_id)
    if not event:
        return False

    text_lower = text.strip().lower()

    # Пропуск события
    if text_lower in ("пропустить", "skip", "назад"):
        _finish_event(player, vk, user_id, "Ты решил не рисковать. Зона подождёт.")
        return True

    # Определяем номер выбора
    choice_idx = None
    if text_lower.isdigit():
        choice_idx = int(text_lower) - 1
    else:
        # Текстовое совпадение с выбором
        stage_index = event.get("_stage_index", 0)
        if event.get("type") == "multi_stage":
            stages = event.get("stages", [])
            if stage_index < len(stages):
                choices = stages[stage_index].get("choices", [])
            else:
                choices = []
        else:
            choices = event.get("choices", [])

        for i, choice in enumerate(choices):
            if choice["label"].lower() == text_lower:
                choice_idx = i
                break
            if text_lower in choice["label"].lower():
                choice_idx = i
                break

    if choice_idx is None:
        stage_index = event.get("_stage_index", 0)
        if event.get("type") == "multi_stage":
            stages = event.get("stages", [])
            if 0 <= stage_index < len(stages):
                choices = stages[stage_index].get("choices", [])
            else:
                choices = []
        else:
            choices = event.get("choices", [])
        max_choice = len(choices)
        if max_choice <= 0:
            _finish_event(player, vk, user_id, "Событие повреждено и было сброшено. Продолжай путь.")
            return True
        _show_event_notice(player, vk, user_id, event, f"Выбери вариант числом от 1 до {max_choice} или нажми 'Пропустить'.")
        return True

    return _process_event_choice(player, vk, user_id, event, choice_idx)


def handle_event_callback(player, vk, user_id: int, payload: dict) -> bool:
    """Обработка inline callback случайного события."""
    event = get_pending_event(user_id)
    if not event:
        return False

    if payload.get("action") == "skip":
        _finish_event(player, vk, user_id, "Ты решил не рисковать. Зона подождёт.")
        return True

    if payload.get("action") != "choice":
        _show_event_notice(player, vk, user_id, event, "Это действие уже устарело.")
        return True

    try:
        choice_idx = int(payload.get("choice"))
    except (TypeError, ValueError):
        _show_event_notice(player, vk, user_id, event, "Это действие уже устарело.")
        return True
    return _process_event_choice(player, vk, user_id, event, choice_idx)


def _process_event_choice(player, vk, user_id: int, event: dict, choice_index: int) -> bool:
    """Обработать выбор игрока в событии"""
    stage_index = event.get("_stage_index", 0)

    result = apply_event_choice(event, choice_index, player, user_id=user_id, stage_index=stage_index)

    if result.get("invalid"):
        _show_event_notice(player, vk, user_id, event, result.get("message", "Неверный выбор."))
        return True

    # Фатальный исход в ивенте: добиваем до 0 и отправляем в больницу.
    if int(getattr(player, "health", 0) or 0) <= 0:
        clear_pending_event(user_id)
        if result.get("message"):
            try_edit_or_send_ui(vk, user_id, "random_event", result["message"])
        from handlers.combat import _handle_death
        _handle_death(
            player,
            vk,
            user_id,
            cause="Смертельная ловушка",
            killer_name="опасность Зоны",
        )
        return True

    # Сохраняем изменения игрока
    database.update_user_stats(
        user_id,
        health=player.health,
        energy=player.energy,
        money=player.money,
        experience=player.experience,
    )

    # Проверяем, есть ли следующая стадия
    next_stage = result.get("next_stage")
    if next_stage is not None:
        # Многоэтапное событие — обновляем стадию и показываем следующий этап
        event["_stage_index"] = next_stage
        set_pending_event(user_id, event)
        show_random_event(player, vk, user_id, event)
        return True

    # Событие завершено — очищаем pending
    _finish_event(player, vk, user_id, result["message"])
    return True


def _show_event_notice(player, vk, user_id: int, event: dict, notice: str):
    stage_index = int(event.get("_stage_index", 0) or 0)
    message = f"{notice}\n\n{format_event_message(event, stage_index)}"
    keyboard = create_random_event_keyboard(event, stage_index=stage_index, inline=True).get_keyboard()
    try_edit_or_send_ui(vk, user_id, "random_event", message, keyboard=keyboard)


def _finish_event(player, vk, user_id: int, message: str):
    clear_pending_event(user_id)
    keyboard = create_resume_keyboard(player.current_location_id, player.level, user_id).get_keyboard()
    try_edit_or_send_ui(vk, user_id, "random_event", message, keyboard=keyboard)
