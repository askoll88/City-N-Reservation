from __future__ import annotations
"""
Обработчики случайных событий
"""
import database
from random_events import apply_event_choice, format_event_message
from state_manager import get_pending_event, set_pending_event, clear_pending_event
from state_manager import get_emission_pending, clear_emission_pending
from handlers.keyboards import create_random_event_keyboard, create_resume_keyboard
from emission import handle_emission_warning_response


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
        clear_pending_event(user_id)
        vk.messages.send(
            user_id=user_id,
            message="Ты решил не рисковать. Зона подождёт.",
            keyboard=create_resume_keyboard(player.current_location_id, player.level, user_id).get_keyboard(),
            random_id=0,
        )
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
            clear_pending_event(user_id)
            vk.messages.send(
                user_id=user_id,
                message="Событие повреждено и было сброшено. Продолжай путь.",
                keyboard=create_resume_keyboard(player.current_location_id, player.level, user_id).get_keyboard(),
                random_id=0,
            )
            return True
        vk.messages.send(
            user_id=user_id,
            message=f"Выбери вариант числом от 1 до {max_choice} или нажми 'Пропустить'.",
            keyboard=create_random_event_keyboard(event, stage_index=stage_index).get_keyboard(),
            random_id=0,
        )
        return True

    return _process_event_choice(player, vk, user_id, event, choice_idx)


def _process_event_choice(player, vk, user_id: int, event: dict, choice_index: int) -> bool:
    """Обработать выбор игрока в событии"""
    stage_index = event.get("_stage_index", 0)

    result = apply_event_choice(event, choice_index, player, user_id=user_id, stage_index=stage_index)

    if result.get("invalid"):
        vk.messages.send(
            user_id=user_id,
            message=result.get("message", "Неверный выбор."),
            keyboard=create_random_event_keyboard(event, stage_index=stage_index).get_keyboard(),
            random_id=0,
        )
        return True

    # Сохраняем изменения игрока
    database.update_user_stats(
        user_id,
        health=player.health,
        energy=player.energy,
        money=player.money,
        experience=player.experience,
        shells=getattr(player, 'shells', 0),
    )

    # Проверяем, есть ли следующая стадия
    next_stage = result.get("next_stage")
    if next_stage is not None:
        # Многоэтапное событие — обновляем стадию и показываем следующий этап
        event["_stage_index"] = next_stage
        set_pending_event(user_id, event)

        msg = format_event_message(event, next_stage)
        keyboard = create_random_event_keyboard(event, stage_index=next_stage).get_keyboard()

        # Для мульти-стадийных событий — редактируем сообщение вместо нового
        msg_id = event.get("_msg_id")
        if msg_id:
            try:
                vk.messages.edit(
                    conversation_message_id=msg_id,
                    message=msg,
                    keyboard=keyboard,
                )
            except Exception:
                # Если редактирование не удалось — отправляем новое
                vk.messages.send(
                    user_id=user_id,
                    message=msg,
                    keyboard=keyboard,
                    random_id=0,
                )
        else:
            vk.messages.send(
                user_id=user_id,
                message=msg,
                keyboard=keyboard,
                random_id=0,
            )
        return True

    # Событие завершено — очищаем pending
    clear_pending_event(user_id)

    vk.messages.send(
        user_id=user_id,
        message=result["message"],
        keyboard=create_resume_keyboard(player.current_location_id, player.level, user_id).get_keyboard(),
        random_id=0,
    )
    return True
