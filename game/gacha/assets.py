"""Local image assets for Resonance Zone SSR items."""

from __future__ import annotations

import logging
from pathlib import Path

from .event_items import get_event_item_image_filename, is_ssr_event_item

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GACHA_IMAGE_DIR = PROJECT_ROOT / "Img" / "gacha"
_ITEM_ATTACHMENT_CACHE: dict[str, str] = {}


def get_item_image_path(item_name: str | None) -> Path | None:
    filename = get_event_item_image_filename(item_name)
    if not filename:
        return None
    return GACHA_IMAGE_DIR / filename


def upload_item_image(vk, user_id: int, item_name: str | None) -> str | None:
    """Upload an SSR event item image to VK and return an attachment string."""
    clean_name = str(item_name or "").strip()
    if not clean_name or not is_ssr_event_item(clean_name):
        return None
    if clean_name in _ITEM_ATTACHMENT_CACHE:
        return _ITEM_ATTACHMENT_CACHE[clean_name]

    image_path = get_item_image_path(clean_name)
    if not image_path or not image_path.exists():
        logger.warning("Картинка SSR Резонанса не найдена: item=%s path=%s", clean_name, image_path)
        return None

    try:
        import requests

        upload_server = vk.photos.getMessagesUploadServer(peer_id=user_id)
        with image_path.open("rb") as image_file:
            upload_response = requests.post(
                upload_server["upload_url"],
                files={"photo": image_file},
                timeout=20,
            )
        upload_response.raise_for_status()
        uploaded = upload_response.json()
        saved = vk.photos.saveMessagesPhoto(
            photo=uploaded["photo"],
            server=uploaded["server"],
            hash=uploaded["hash"],
        )
        if not saved:
            return None

        photo = saved[0]
        attachment = f"photo{photo['owner_id']}_{photo['id']}"
        access_key = photo.get("access_key")
        if access_key:
            attachment = f"{attachment}_{access_key}"

        _ITEM_ATTACHMENT_CACHE[clean_name] = attachment
        return attachment
    except Exception:
        logger.exception("Не удалось загрузить картинку SSR Резонанса: user_id=%s item=%s", user_id, clean_name)
        return None


def first_ssr_attachment(vk, user_id: int, rewards: list) -> str | None:
    for reward in rewards or []:
        if getattr(reward, "rarity", None) == "SSR":
            item_name = getattr(reward, "source_name", None) or getattr(reward, "name", None)
            attachment = upload_item_image(vk, user_id, item_name)
            if attachment:
                return attachment
    return None
