from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock

from schemas.communication import CommunicationCreate, CommunicationRead
from services.communication_service import CommunicationService
from telegram.review import build_communication_history
from utils.enums import ContactStatus


class CommunicationServiceTest(IsolatedAsyncioTestCase):
    async def test_incoming_message_updates_contact(self) -> None:
        contact = SimpleNamespace(
            id=7,
            status=ContactStatus.SENT.value,
            response=None,
            next_action=None,
            last_contact_at=None,
            preferred_channel="email",
        )
        session = SimpleNamespace(
            flush=AsyncMock(),
            commit=AsyncMock(),
            rollback=AsyncMock(),
        )
        service = CommunicationService.__new__(CommunicationService)
        service.session = session
        service.contact_repository = SimpleNamespace(
            get_by_id=AsyncMock(return_value=contact)
        )
        communication = SimpleNamespace(id=11)
        service.repository = SimpleNamespace(
            create=AsyncMock(return_value=communication)
        )

        result = await service.create(
            CommunicationCreate(
                contact_id=7,
                channel="email",
                direction="incoming",
                message="Нам интересно участие.",
                status="received",
            )
        )

        self.assertIs(result, communication)
        self.assertEqual(contact.status, ContactStatus.REPLIED.value)
        self.assertEqual(contact.response, "Нам интересно участие.")
        self.assertEqual(
            contact.next_action,
            "Оценить ответ и определить следующее действие",
        )
        session.commit.assert_awaited_once()


class CommunicationHistoryPresentationTest(TestCase):
    def test_read_schema_contains_timestamp(self) -> None:
        item = CommunicationRead(
            id=1,
            contact_id=7,
            channel="email",
            direction="outgoing",
            message="Здравствуйте",
            status="sent",
            created_at=datetime(2026, 7, 26, 10, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(item.created_at.year, 2026)

    def test_builds_chronological_history(self) -> None:
        text = build_communication_history(
            [
                {
                    "channel": "email",
                    "direction": "outgoing",
                    "message": "Здравствуйте",
                    "status": "sent",
                    "created_at": "2026-07-26T10:30:00+00:00",
                },
                {
                    "channel": "email",
                    "direction": "incoming",
                    "message": "Нам интересно",
                    "status": "received",
                    "created_at": "2026-07-27T09:00:00+00:00",
                },
            ]
        )
        self.assertIn("→ Исходящее", text)
        self.assertIn("← Входящее", text)
        self.assertLess(text.index("Здравствуйте"), text.index("Нам интересно"))

    def test_global_history_shows_organization(self) -> None:
        text = build_communication_history(
            [
                {
                    "organization_name": "Краеведческий музей",
                    "channel": "email",
                    "direction": "outgoing",
                    "message": "Приглашение",
                    "status": "sent",
                    "created_at": "2026-07-26T10:30:00+00:00",
                }
            ]
        )
        self.assertIn("Краеведческий музей", text)
