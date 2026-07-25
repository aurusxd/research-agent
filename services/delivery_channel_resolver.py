from typing import Any


SUPPORTED_CHANNELS = {
    "email",
    "contact_form",
    "vk",
    "telegram",
    "ok",
}

CHANNEL_ALIASES = {
    "form": "contact_form",
    "website_form": "contact_form",
    "ok.ru": "ok",
    "odnoklassniki": "ok",
}


class DeliveryChannelResolutionError(RuntimeError):
    pass


def resolve_delivery_channel(contact: Any) -> str:
    """Проверяет выбор агента, не меняя его приоритет."""
    raw_channel = (contact.preferred_channel or "").strip().lower()
    channel = CHANNEL_ALIASES.get(raw_channel, raw_channel)
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
            getattr(contact, "recipient_external_id", None)
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
