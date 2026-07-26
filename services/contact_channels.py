from types import SimpleNamespace
from typing import Any, Mapping

from services.delivery_channel_resolver import (
    DeliveryChannelResolutionError,
    resolve_delivery_channel,
)

def has_usable_contact_channel(data: Any) -> bool:
    if isinstance(data, Mapping):
        data = SimpleNamespace(**data)
    try:
        resolve_delivery_channel(data)
    except DeliveryChannelResolutionError:
        return False
    return True


def require_usable_contact_channel(data: Any) -> None:
    if not has_usable_contact_channel(data):
        raise ValueError(
            "Для контакта должны быть заполнены preferred_channel и адрес "
            "получателя именно для этого канала: email, официальная форма, "
            "VK, Telegram или Одноклассники"
        )
