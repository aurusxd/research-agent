from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from database.models.communication import Communication
from database.repositories.communication_repository import (
    CommunicationRepository,
)
from database.repositories.contact_repository import ContactRepository
from services.email_sender import send_yandex_email
from utils.enums import CommunicationStatus, ContactStatus


class ContactMailingError(RuntimeError):
    pass


class ContactAlreadySentError(ContactMailingError):
    pass


class ContactNotReadyError(ContactMailingError):
    pass


class ContactMailingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.contact_repository = ContactRepository(session)
        self.communication_repository = CommunicationRepository(session)

    async def send_approved_email(
        self,
        contact_id: int,
        *,
        subject: str | None = None,
    ) -> tuple[Communication, str]:
        contact = await self.contact_repository.get_by_id(contact_id)
        if contact is None:
            raise ContactMailingError("Контакт не найден")

        if contact.status == ContactStatus.SENT.value:
            raise ContactAlreadySentError("Письмо этому контакту уже отправлено")

        previous = await self.communication_repository.get_by_contact_id(
            contact_id,
            limit=100,
        )
        if any(
            item.direction == "outgoing"
            and item.channel == "email"
            and item.status == CommunicationStatus.SENT.value
            for item in previous
        ):
            raise ContactAlreadySentError("Письмо этому контакту уже отправлено")

        if contact.status not in {
            ContactStatus.APPROVED.value,
            ContactStatus.FAILED.value,
        }:
            raise ContactNotReadyError(
                "Перед отправкой контакт должен быть одобрен оператором"
            )

        recipient = (
            contact.email
            or contact.recipient_address
            or ""
        ).strip()
        if not recipient:
            raise ContactNotReadyError("У контакта отсутствует email")

        message = (contact.generated_message or "").strip()
        if not message:
            raise ContactNotReadyError(
                "У контакта отсутствует текст приглашения"
            )

        email_subject = (
            (subject or "").strip()
            or "Приглашение к участию в проекте «Корни»"
        )

        try:
            result = await send_yandex_email(
                recipient=recipient,
                subject=email_subject,
                text=message,
            )
        except Exception as error:
            communication = await self.communication_repository.create(
                {
                    "contact_id": contact.id,
                    "channel": "email",
                    "direction": "outgoing",
                    "message": message,
                    "status": CommunicationStatus.FAILED.value,
                }
            )
            contact.status = ContactStatus.FAILED.value
            contact.next_action = "Проверить ошибку отправки и повторить вручную"
            contact.last_contact_at = datetime.now(timezone.utc)
            await self.session.commit()
            raise ContactMailingError(str(error)) from error

        communication = await self.communication_repository.create(
            {
                "contact_id": contact.id,
                "channel": "email",
                "direction": "outgoing",
                "message": message,
                "status": CommunicationStatus.SENT.value,
            }
        )
        contact.status = ContactStatus.SENT.value
        contact.preferred_channel = "email"
        contact.recipient_address = recipient
        contact.next_action = "Ожидать ответ"
        contact.last_contact_at = datetime.now(timezone.utc)
        await self.session.commit()

        return communication, str(result.get("message_id", ""))
