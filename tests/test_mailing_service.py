from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from services.mailing_service import (
    ContactAlreadySentError,
    ContactMailingService,
)
from services.email_sender import EmailConfigurationError
from utils.enums import ContactStatus


class ContactMailingServiceTest(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.contact = SimpleNamespace(
            id=1,
            email="museum@example.org",
            recipient_address=None,
            preferred_channel="email",
            generated_message="Здравствуйте! Приглашаем вас в проект.",
            status=ContactStatus.APPROVED.value,
            next_action=None,
            last_contact_at=None,
        )
        self.session = SimpleNamespace(commit=AsyncMock())
        self.service = ContactMailingService.__new__(
            ContactMailingService
        )
        self.service.session = self.session
        self.service.contact_repository = SimpleNamespace(
            get_by_id=AsyncMock(return_value=self.contact)
        )
        self.service.communication_repository = SimpleNamespace(
            get_by_contact_id=AsyncMock(return_value=[]),
            create=AsyncMock(return_value=SimpleNamespace(id=42)),
        )

    @patch(
        "services.mailing_service.send_yandex_email",
        new_callable=AsyncMock,
    )
    async def test_send_approved_email(self, send_email: AsyncMock) -> None:
        send_email.return_value = {"message_id": "message-1"}

        communication, message_id = (
            await self.service.send_approved_email(self.contact.id)
        )

        self.assertEqual(communication.id, 42)
        self.assertEqual(message_id, "message-1")
        self.assertEqual(self.contact.status, ContactStatus.SENT.value)
        self.assertEqual(self.contact.next_action, "Ожидать ответ")
        self.session.commit.assert_awaited_once()

    async def test_does_not_send_twice(self) -> None:
        self.contact.status = ContactStatus.SENT.value

        with self.assertRaises(ContactAlreadySentError):
            await self.service.send_approved_email(self.contact.id)

    @patch(
        "services.mailing_service.send_yandex_email",
        new_callable=AsyncMock,
    )
    async def test_marks_failed_send(self, send_email: AsyncMock) -> None:
        send_email.side_effect = EmailConfigurationError(
            "YANDEX_SMTP_USER не заполнен"
        )

        with self.assertRaises(Exception):
            await self.service.send_approved_email(self.contact.id)

        self.assertEqual(self.contact.status, ContactStatus.FAILED.value)
        self.assertEqual(
            self.contact.next_action,
            "Проверить ошибку отправки и повторить вручную",
        )
        self.session.commit.assert_awaited_once()
