import os
import sys
from types import ModuleType, SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

fake_session_module = ModuleType("database.session")
fake_session_module.provider = SimpleNamespace(session_factory=None)
sys.modules.setdefault("database.session", fake_session_module)

from services.mailing_queue_service import MailingQueueController


class MailingQueueControllerTest(IsolatedAsyncioTestCase):
    async def test_status_reports_queue_limits_and_timezone(self) -> None:
        controller = MailingQueueController()
        controller._count_approved = AsyncMock(return_value=3)
        controller._sent_today = AsyncMock(return_value=7)

        with patch.dict(
            os.environ,
            {
                "MAILING_INTERVAL_SECONDS": "15",
                "MAILING_DAILY_LIMIT": "25",
                "MAILING_TIMEZONE": "Asia/Novosibirsk",
            },
        ):
            status = await controller.status()

        self.assertEqual(status["state"], "stopped")
        self.assertEqual(status["approved_pending"], 3)
        self.assertEqual(status["sent_today"], 7)
        self.assertEqual(status["interval_seconds"], 15)
        self.assertEqual(status["daily_limit"], 25)
        self.assertEqual(status["timezone"], "Asia/Novosibirsk")

    async def test_stop_cancels_running_worker(self) -> None:
        controller = MailingQueueController()
        controller._count_approved = AsyncMock(return_value=0)
        controller._sent_today = AsyncMock(return_value=0)
        controller._run = AsyncMock()

        await controller.start()
        status = await controller.stop()

        self.assertEqual(status["state"], "stopped")
        self.assertIsNone(controller._task)
