QUEUE_BY_CHANNEL = {
    "email": "mailing_email",
    "telegram": "mailing_telegram",
    "vk": "mailing_vk",
}


def queue_for_channel(preferred_channel: str | None) -> str:
    channel = (preferred_channel or "email").strip().lower()
    return QUEUE_BY_CHANNEL.get(channel, "mailing_email")
