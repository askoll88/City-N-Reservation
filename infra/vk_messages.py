"""Safe VK message transport helpers.

All game messages should go through this module when a call site is touched.
The helpers keep VK-specific defaults in one place and make fallback behavior
consistent across text, keyboards, attachments, edits, and callback answers.
"""
from __future__ import annotations

import logging
import json
from typing import Any

logger = logging.getLogger(__name__)

SAFE_SEND_DEFAULTS = {
    "disable_mentions": 1,
    "dont_parse_links": 1,
}


def _keyboard_payload(keyboard: Any) -> Any:
    if keyboard is None:
        return None
    return keyboard.get_keyboard() if hasattr(keyboard, "get_keyboard") else keyboard


def _clean_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


def build_send_kwargs(
    *,
    user_id: int | None = None,
    peer_id: int | None = None,
    message: str = "",
    keyboard: Any = None,
    attachment: str | None = None,
    random_id: int = 0,
    **extra: Any,
) -> dict[str, Any]:
    """Build kwargs for messages.send with safe defaults."""
    kwargs = {
        **SAFE_SEND_DEFAULTS,
        "user_id": user_id,
        "peer_id": peer_id,
        "message": message,
        "keyboard": _keyboard_payload(keyboard),
        "attachment": attachment,
        "random_id": random_id,
        **extra,
    }
    return _clean_kwargs(kwargs)


def send(
    vk,
    *,
    user_id: int | None = None,
    peer_id: int | None = None,
    message: str = "",
    keyboard: Any = None,
    attachment: str | None = None,
    fallback_without_attachment: bool = True,
    **extra: Any,
):
    """Send a VK message with safe defaults and optional attachment fallback."""
    kwargs = build_send_kwargs(
        user_id=user_id,
        peer_id=peer_id,
        message=message,
        keyboard=keyboard,
        attachment=attachment,
        **extra,
    )

    try:
        return vk.messages.send(**kwargs)
    except Exception:
        if not attachment or not fallback_without_attachment:
            logger.exception("VK messages.send failed")
            raise

        logger.exception("VK messages.send failed with attachment, retrying without attachment")
        kwargs.pop("attachment", None)
        return vk.messages.send(**kwargs)


def edit(
    vk,
    *,
    message: str,
    keyboard: Any = None,
    attachment: str | None = None,
    **extra: Any,
):
    """Edit a VK message using the same safe text defaults."""
    kwargs = _clean_kwargs(
        {
            **SAFE_SEND_DEFAULTS,
            "message": message,
            "keyboard": _keyboard_payload(keyboard),
            "attachment": attachment,
            **extra,
        }
    )
    return vk.messages.edit(**kwargs)


def answer_event(
    vk,
    *,
    event_id: str,
    user_id: int,
    peer_id: int,
    text: str | None = None,
    show_snackbar: bool = False,
    **extra: Any,
):
    """Answer a callback event, optionally as a snackbar."""
    kwargs = {
        "event_id": event_id,
        "user_id": user_id,
        "peer_id": peer_id,
        **extra,
    }
    if text:
        kwargs["event_data"] = json.dumps(
            {"type": "show_snackbar", "text": text},
            ensure_ascii=False,
        )
    return vk.messages.send_message_event_answer(**kwargs)
