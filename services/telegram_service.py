import os
from typing import Any

import httpx


class TelegramConfigurationError(RuntimeError):
    pass


class TelegramSendError(RuntimeError):
    pass


def _required_token() -> str:
    token = os.getenv("TELEGRAM_OUTREACH_BOT_TOKEN", "").strip()
    if not token:
        raise TelegramConfigurationError(
            "Не задана обязательная переменная окружения "
            "TELEGRAM_OUTREACH_BOT_TOKEN"
        )
    return token


class TelegramService:
    @staticmethod
    async def send_message(
        *,
        recipient_external_id: str,
        text: str,
    ) -> dict[str, Any]:
        token = _required_token()
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                json={
                    "chat_id": recipient_external_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )

        try:
            data = response.json()
        except ValueError as error:
            raise TelegramSendError(
                f"Telegram вернул некорректный ответ: {response.text[:500]}"
            ) from error

        if response.is_error or data.get("ok") is not True:
            raise TelegramSendError(
                str(data.get("description") or response.text)[:500]
            )

        result = data.get("result") or {}
        return {
            "success": True,
            "message_id": str(result.get("message_id", "")),
        }

    @staticmethod
    async def notify_operator(text: str) -> None:
        token = os.getenv("BOT_TOKEN", "").strip()
        chat_id = os.getenv("OPERATOR_TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            return
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )

    @staticmethod
    async def notify_chat(chat_id: str, text: str) -> None:
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token or not chat_id.strip():
            raise TelegramConfigurationError(
                "Не заданы BOT_TOKEN или chat_id для уведомления"
            )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
        if response.is_error:
            raise TelegramSendError(
                f"Не удалось отправить отчёт о поиске: {response.text[:500]}"
            )
