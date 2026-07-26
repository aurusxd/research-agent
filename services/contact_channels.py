from typing import Any, Mapping

from services.delivery_channel_resolver import (
    SUPPORTED_CHANNELS,
    _normalized_channel,
)


DIRECT_CHANNEL_FIELDS = (
    "email",
    "contact_form_url",
    "vk_url",
    "telegram_url",
    "ok_url",
)


def _value(data: Any, field: str) -> Any:
    if isinstance(data, Mapping):
        return data.get(field)
    return getattr(data, field, None)


def _present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def has_usable_contact_channel(data: Any) -> bool:
    if any(_present(_value(data, field)) for field in DIRECT_CHANNEL_FIELDS):
        return True

    if _present(_value(data, "recipient_external_id")):
        channel = _normalized_channel(_value(data, "preferred_channel"))
        return channel == "telegram"

    if _present(_value(data, "recipient_address")):
        channel = _normalized_channel(_value(data, "preferred_channel"))
        return channel in SUPPORTED_CHANNELS

    return False


def require_usable_contact_channel(data: Any) -> None:
    if not has_usable_contact_channel(data):
        raise ValueError(
            "Контакт не содержит доступного канала связи: нужны email, "
            "официальная форма, VK, Telegram или Одноклассники"
        )
