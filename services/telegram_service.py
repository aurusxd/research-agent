import os
import re
from pathlib import Path
from typing import Any

import httpx
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PeerFloodError,
    SessionPasswordNeededError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
    UserPrivacyRestrictedError,
)


class TelegramConfigurationError(RuntimeError):
    pass


class TelegramSessionExpired(RuntimeError):
    pass


class TelegramRequiresHuman(RuntimeError):
    pass


class TelegramSendError(RuntimeError):
    pass


def extract_username(recipient: str) -> str:
    value = recipient.strip()

    match = re.fullmatch(
        r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/@?([A-Za-z0-9_]{5,32})/?",
        value,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    if re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value):
        return value[1:]

    raise TelegramConfigurationError(
        "Для Telegram требуется публичный @username или ссылка https://t.me/username"
    )


def build_client() -> TelegramClient:
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = os.getenv(
        "TELEGRAM_USER_SESSION",
        "/app/telegram-session/outreach",
    ).strip()

    if not api_id or not api_hash:
        raise TelegramConfigurationError(
            "Не заданы TELEGRAM_API_ID и TELEGRAM_API_HASH"
        )

    Path(session).parent.mkdir(parents=True, exist_ok=True)

    return TelegramClient(
        session,
        int(api_id),
        api_hash,
    )


class TelegramService:
    @staticmethod
    async def send_message(
        *,
        recipient_external_id: str = "",
        recipient_address: str = "",
        text: str,
    ) -> dict[str, Any]:
        recipient = recipient_address or recipient_external_id
        username = extract_username(recipient)
        client = build_client()

        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise TelegramSessionExpired(
                    "Пользовательская Telegram-сессия не авторизована"
                )

            entity = await client.get_entity(username)
            message = await client.send_message(
                entity,
                text,
                link_preview=False,
            )

            return {
                "success": True,
                "message_id": str(message.id),
            }

        except FloodWaitError as error:
            raise TelegramRequiresHuman(
                f"Telegram установил ограничение: повтор возможен через "
                f"{error.seconds} секунд"
            ) from error
        except PeerFloodError as error:
            raise TelegramRequiresHuman(
                "Telegram ограничил исходящие обращения аккаунта"
            ) from error
        except UserPrivacyRestrictedError as error:
            raise TelegramSendError(
                "Настройки приватности получателя запрещают сообщение"
            ) from error
        except (UsernameInvalidError, UsernameNotOccupiedError) as error:
            raise TelegramSendError(
                f"Публичный Telegram username @{username} не найден"
            ) from error
        finally:
            await client.disconnect()

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
    @staticmethod
    async def notify_operator(text: str) -> None:
        chat_id = os.getenv("OPERATOR_TELEGRAM_CHAT_ID", "").strip()
        if not chat_id:
            raise TelegramConfigurationError(
                "Не задан OPERATOR_TELEGRAM_CHAT_ID для уведомления"
            )
        await TelegramService.notify_chat(
            chat_id,
            text,
        )
