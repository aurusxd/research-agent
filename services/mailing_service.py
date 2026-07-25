from datetime import datetime, timezone
import os

from sqlalchemy.ext.asyncio import AsyncSession

from database.models.communication import Communication
from database.repositories.communication_repository import (
    CommunicationRepository,
)
from database.repositories.contact_repository import ContactRepository
from services.email_sender import send_yandex_email
from services.channel_sender import send_telegram_message, send_vk_message
from services.delivery_errors import VkCaptchaRequired, VkSessionExpired
from services.logger import log
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
            ContactStatus.QUEUED.value,
            ContactStatus.FAILED.value,
            ContactStatus.SENDING.value,
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
        except (VkCaptchaRequired, VkSessionExpired) as error:
            await self.communication_repository.create(
                {
                    "contact_id": contact.id,
                    "channel": channel,
                    "direction": "outgoing",
                    "message": message,
                    "status": CommunicationStatus.FAILED.value,
                }
            )
            contact.status = ContactStatus.REQUIRES_HUMAN.value
            contact.next_action = str(error)
            contact.last_contact_at = datetime.now(timezone.utc)
            await self.session.commit()
            raise ContactMailingError(str(error)) from error
        except Exception as error:
            log.exception(
                "Не удалось отправить email контакту ID={}",
                contact.id,
            )
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

    async def send_approved(
        self,
        contact_id: int,
        *,
        subject: str | None = None,
    ) -> tuple[Communication, str]:
        contact = await self.contact_repository.get_by_id(contact_id)
        if contact is None:
            raise ContactMailingError("Контакт не найден")

        channel = (contact.preferred_channel or "").strip().lower()
        if os.getenv("MAILING_DRY_RUN", "true").lower() == "true":
            return await self._record_dry_run(contact, channel or "email")
        if channel in {"", "email"}:
            return await self.send_approved_email(
                contact_id,
                subject=subject,
            )
        if channel not in {"vk", "telegram"}:
            raise ContactNotReadyError(
                f"Автоматическая отправка для канала {channel!r} не поддерживается"
            )
        return await self._send_approved_social(contact, channel)

    async def _record_dry_run(
        self,
        contact,
        channel: str,
    ) -> tuple[Communication, str]:
        message = (contact.generated_message or "").strip()
        if not message:
            raise ContactNotReadyError(
                "У контакта отсутствует текст приглашения"
            )
        communication = await self.communication_repository.create(
            {
                "contact_id": contact.id,
                "channel": channel,
                "direction": "outgoing",
                "message": message,
                "status": CommunicationStatus.DRY_RUN.value,
            }
        )
        contact.status = ContactStatus.DRY_RUN.value
        contact.next_action = "Dry-run завершён, реальная отправка не выполнялась"
        contact.last_contact_at = datetime.now(timezone.utc)
        await self.session.commit()
        return communication, f"dry-run-{communication.id}"

    async def _send_approved_social(
        self,
        contact,
        channel: str,
    ) -> tuple[Communication, str]:
        if contact.status == ContactStatus.SENT.value:
            raise ContactAlreadySentError(
                "Сообщение этому контакту уже отправлено"
            )
        if contact.status not in {
            ContactStatus.APPROVED.value,
            ContactStatus.QUEUED.value,
            ContactStatus.FAILED.value,
            ContactStatus.SENDING.value,
        }:
            raise ContactNotReadyError(
                "Перед отправкой контакт должен быть одобрен оператором"
            )

        previous = await self.communication_repository.get_by_contact_id(
            contact.id,
            limit=100,
        )
        if any(
            item.direction == "outgoing"
            and item.channel == channel
            and item.status == CommunicationStatus.SENT.value
            for item in previous
        ):
            raise ContactAlreadySentError(
                "Сообщение этому контакту уже отправлено"
            )

        message = (contact.generated_message or "").strip()
        if not message:
            raise ContactNotReadyError(
                "У контакта отсутствует текст приглашения"
            )

        try:
            if channel == "vk":
                recipient = (
                    contact.recipient_address
                    or contact.vk_url
                    or ""
                ).strip()
                if not recipient:
                    raise ContactNotReadyError(
                        "Для VK отсутствует URL профиля или сообщества"
                    )
                result = await send_vk_message(
                    recipient_url=recipient,
                    text=message,
                )
            else:
                recipient = (contact.recipient_external_id or "").strip()
                if not recipient:
                    raise ContactNotReadyError(
                        "Для Telegram отсутствует recipient_external_id"
                    )
                result = await send_telegram_message(
                    recipient_external_id=recipient,
                    text=message,
                )
        except Exception as error:
            await self.communication_repository.create(
                {
                    "contact_id": contact.id,
                    "channel": channel,
                    "direction": "outgoing",
                    "message": message,
                    "status": CommunicationStatus.FAILED.value,
                }
            )
            contact.status = ContactStatus.FAILED.value
            contact.next_action = (
                f"Проверить настройки {channel} и повторно одобрить контакт"
            )
            contact.last_contact_at = datetime.now(timezone.utc)
            await self.session.commit()
            raise ContactMailingError(str(error)) from error

        communication = await self.communication_repository.create(
            {
                "contact_id": contact.id,
                "channel": channel,
                "direction": "outgoing",
                "message": message,
                "status": CommunicationStatus.SENT.value,
            }
        )
        contact.status = ContactStatus.SENT.value
        contact.recipient_address = (
            contact.recipient_address or recipient
        )
        contact.next_action = "Ожидать ответ"
        contact.last_contact_at = datetime.now(timezone.utc)
        await self.session.commit()
        return communication, str(result.get("message_id", ""))
