from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from worker.tasks import _notify_delivery_error, _screenshot_path


class ScreenshotPathTest(TestCase):
    def test_extracts_screenshot_path_from_error(self) -> None:
        error = (
            "VK не подтвердил отправку. Screenshot: "
            "/app/smoke-artifacts/vk-send-not-confirmed-20260727.png"
        )

        self.assertEqual(
            _screenshot_path(error),
            "/app/smoke-artifacts/vk-send-not-confirmed-20260727.png",
        )

    def test_returns_none_without_screenshot(self) -> None:
        self.assertIsNone(_screenshot_path("VK временно недоступен"))


class DeliveryErrorNotificationTest(IsolatedAsyncioTestCase):
    @patch(
        "worker.tasks.TelegramService.notify_operator_with_photo",
        new_callable=AsyncMock,
    )
    async def test_sends_fallback_error_with_screenshot(
        self,
        notify: AsyncMock,
    ) -> None:
        await _notify_delivery_error(
            {
                "contact_id": 16,
                "status": "fallback",
                "fallback_channel": "telegram",
                "failed_channel": "vk",
                "error": (
                    "VK не подтвердил отправку. Screenshot: "
                    "/app/smoke-artifacts/failure.png"
                ),
            }
        )

        notify.assert_awaited_once()
        text, screenshot = notify.await_args.args
        self.assertIn("Контакт: ID=16", text)
        self.assertIn("Канал: vk", text)
        self.assertIn("Следующая попытка: канал telegram", text)
        self.assertEqual(screenshot, "/app/smoke-artifacts/failure.png")

    @patch(
        "worker.tasks.TelegramService.notify_operator",
        new_callable=AsyncMock,
    )
    async def test_sends_text_when_error_has_no_screenshot(
        self,
        notify: AsyncMock,
    ) -> None:
        await _notify_delivery_error(
            {
                "contact_id": 4,
                "status": "failed",
                "channel": "email",
                "error": "SMTP недоступен",
            }
        )

        notify.assert_awaited_once()
        self.assertIn("SMTP недоступен", notify.await_args.args[0])

    @patch(
        "worker.tasks.TelegramService.notify_operator_with_photo",
        new_callable=AsyncMock,
    )
    async def test_notifies_about_retryable_attempt_immediately(
        self,
        notify: AsyncMock,
    ) -> None:
        await _notify_delivery_error(
            {
                "contact_id": 14,
                "status": "retrying",
                "retry_attempt": 2,
                "channel": "vk",
                "error": (
                    "VK временно недоступен. Screenshot: "
                    "/app/smoke-artifacts/retry.png"
                ),
            }
        )

        notify.assert_awaited_once()
        text, _ = notify.await_args.args
        self.assertIn("Статус: retrying", text)
        self.assertIn("неудачная попытка №2", text)
