from typing import Any


def build_review_card(contact: dict[str, Any]) -> str:
    """Формирует читаемую карточку контакта для проверки."""
    organization = contact.get("organization_name") or "Без названия"
    score = contact.get("relevance_score")
    score_text = f"{score}/100" if score is not None else "не указана"
    channel = contact.get("preferred_channel") or "не выбран"
    recipient = contact.get("recipient_address") or "не указан"
    reason = contact.get("relevance_reason") or "не указана"
    draft = contact.get("generated_message") or "не подготовлен"
    source = contact.get("source") or "не указан"

    card = (
        f"Организация: {organization}\n"
        f"Релевантность: {score_text}\n"
        f"Канал: {channel}\n"
        f"Получатель: {recipient}\n"
        f"Источник: {source}\n\n"
        f"Причина релевантности:\n{reason}\n\n"
        f"Черновик:\n{draft}"
    )

    # Telegram принимает не более 4096 символов в одном сообщении.
    if len(card) > 4096:  # noqa: PLR2004
        card = f"{card[:4050].rstrip()}\n\n[Текст сокращён]"

    return card
