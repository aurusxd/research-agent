from typing import Any


SUPPORTED_CHANNELS = {
    "email",
    "contact_form",
    "vk",
    "telegram",
    "ok",
}

CHANNEL_PRIORITY = (
    "email",
    "contact_form",
    "vk",
    "telegram",
    "ok",
)

CHANNEL_ALIASES = {
    "form": "contact_form",
    "website_form": "contact_form",
    "ok.ru": "ok",
    "odnoklassniki": "ok",
}


class DeliveryChannelResolutionError(RuntimeError):
    pass


def _normalized_channel(channel: str | None) -> str:
    raw_channel = (channel or "").strip().lower()
    return CHANNEL_ALIASES.get(raw_channel, raw_channel)


def recipient_for_channel(contact: Any, channel: str) -> str | None:
    recipients = {
        "email": getattr(contact, "email", None),
        "contact_form": getattr(contact, "contact_form_url", None),
        "vk": getattr(contact, "vk_url", None),
        "telegram": (
            getattr(contact, "telegram_url", None)
            or getattr(contact, "recipient_external_id", None)
        ),
        "ok": getattr(contact, "ok_url", None),
    }
    recipient = recipients.get(channel)
    if not isinstance(recipient, str):
        return None
    return recipient.strip() or None


def resolve_fallback_channel(
    contact: Any,
    failed_channels: set[str],
) -> tuple[str, str] | None:
    excluded = {
        _normalized_channel(channel)
        for channel in failed_channels
    }
    excluded.add(_normalized_channel(contact.preferred_channel))

    for channel in CHANNEL_PRIORITY:
        if channel in excluded:
            continue
        recipient = recipient_for_channel(contact, channel)
        if recipient:
            return channel, recipient
    return None


def resolve_delivery_channel(contact: Any) -> str:
    """Проверяет выбор агента, не меняя его приоритет."""
    channel = _normalized_channel(contact.preferred_channel)
    if not channel:
        raise DeliveryChannelResolutionError(
            "Агент не выбрал preferred_channel"
        )
    if channel not in SUPPORTED_CHANNELS:
        raise DeliveryChannelResolutionError(
            f"Канал {channel!r}, выбранный агентом, не поддерживается"
        )

    has_recipient = {
        "email": bool(
            getattr(contact, "email", None)
            or getattr(contact, "recipient_address", None)
        ),
        "contact_form": bool(
            getattr(contact, "contact_form_url", None)
            or getattr(contact, "recipient_address", None)
        ),
        "vk": bool(
            getattr(contact, "vk_url", None)
            or getattr(contact, "recipient_address", None)
        ),
        "telegram": bool(
            getattr(contact, "telegram_url", None)
            or getattr(contact, "recipient_external_id", None)
            or getattr(contact, "recipient_address", None)
        ),
        "ok": bool(
            getattr(contact, "ok_url", None)
            or getattr(contact, "recipient_address", None)
        ),
    }[channel]
    if not has_recipient:
        raise DeliveryChannelResolutionError(
            f"Агент выбрал {channel}, но адрес получателя отсутствует"
        )
    return channel
