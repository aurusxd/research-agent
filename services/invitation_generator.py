from typing import Any


def build_fallback_invitation(
    *,
    organization_name: str,
    category: str | None,
    preferred_channel: str | None,
) -> str:
    """Builds a safe draft when the search agent omitted generated_message."""
    organization = organization_name.strip()
    activity = (category or "сохранения истории и культурной памяти").strip()
    channel = (preferred_channel or "").strip().lower()

    if channel in {"vk", "telegram", "ok", "contact_form"}:
        return (
            f"Здравствуйте! Обращаемся к команде «{organization}». "
            f"Мы нашли информацию о вашей работе в направлении «{activity}» "
            "и хотим предложить познакомиться с проектом «Корни». Проект "
            "объединяет людей и организации, которые сохраняют семейную, "
            "историческую и культурную память. Будем рады обсудить, может ли "
            "участие в проекте быть вам интересно."
        )

    return (
        f"Здравствуйте!\n\nОбращаемся к команде «{organization}». Мы нашли "
        f"информацию о вашей работе в направлении «{activity}» и хотим "
        "предложить познакомиться с проектом «Корни».\n\nПроект объединяет "
        "людей и организации, которые сохраняют семейную, историческую и "
        "культурную память. Будем рады обсудить, может ли участие в проекте "
        "быть вам интересно."
    )


def ensure_invitation(
    generated_message: str | None,
    *,
    organization_name: str,
    category: str | None,
    preferred_channel: str | None,
) -> str:
    message = (generated_message or "").strip()
    if message:
        return message
    return build_fallback_invitation(
        organization_name=organization_name,
        category=category,
        preferred_channel=preferred_channel,
    )


def ensure_contact_invitation(contact: Any) -> str:
    return ensure_invitation(
        getattr(contact, "generated_message", None),
        organization_name=contact.organization_name,
        category=getattr(contact, "category", None),
        preferred_channel=getattr(contact, "preferred_channel", None),
    )
