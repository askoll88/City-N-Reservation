"""
Обработчики случайных событий
"""
import database
from random_events import apply_event_choice, format_event_message
from state_manager import get_pending_event, clear_pending_event
from handlers.keyboards import create_random_event_keyboard, create_location_keyboard


def handle_event_response(player, vk, user_id: int, text: str) -> bool:
    """Обработка ответа на случайное событие"""
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
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return True

    # Цифра - выбор варианта
    if text_lower.isdigit():
        choice_idx = int(text_lower) - 1
        return _process_event_choice(player, vk, user_id, event, choice_idx)

    # Текстовое совпадение с выбором
    for i, choice in enumerate(event.get("choices", [])):
        if choice["label"].lower() == text_lower:
            return _process_event_choice(player, vk, user_id, event, i)
        # Частичное совпадение
        if text_lower in choice["label"].lower():
            return _process_event_choice(player, vk, user_id, event, i)

    return False


def _process_event_choice(player, vk, user_id: int, event: dict, choice_index: int) -> bool:
    """Обработать выбор игрока в событии"""
    result_msg = apply_event_choice(event, choice_index, player, user_id=user_id)

    # Сохраняем изменения игрока
    database.update_user_stats(
        user_id,
        health=player.health,
        energy=player.energy,
        money=player.money,
        experience=player.experience,
        shells=getattr(player, 'shells', 0),
    )

    clear_pending_event(user_id)

    vk.messages.send(
        user_id=user_id,
        message=result_msg,
        keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
        random_id=0,
    )
    return True
