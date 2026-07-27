import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    ChatWriteForbiddenError,
    FloodWaitError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    PeerFloodError,
    UserAlreadyParticipantError,
    UserPrivacyRestrictedError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import (
    CheckChatInviteRequest,
    ImportChatInviteRequest,
)
from telethon.tl.types import User


class TelegramConfigurationError(RuntimeError):
    pass


class TelegramSessionExpired(RuntimeError):
    pass


class TelegramRequiresHuman(RuntimeError):
    pass


class TelegramSendError(RuntimeError):
    pass


@dataclass(frozen=True)
class TelegramTarget:
    kind: Literal["public", "invite"]
    value: str


def parse_telegram_target(recipient: str) -> TelegramTarget:
    value = recipient.strip()

    invite_match = re.fullmatch(
        r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/"
        r"(?:joinchat/|\+)([A-Za-z0-9_-]+)/*",
        value,
        re.IGNORECASE,
    )
    if invite_match:
        return TelegramTarget("invite", invite_match.group(1))

    public_match = re.fullmatch(
        r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/"
        r"@?([A-Za-z0-9_]{5,32})/*",
        value,
        re.IGNORECASE,
    )
    if public_match:
        return TelegramTarget("public", public_match.group(1))

    if re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value):
        return TelegramTarget("public", value[1:])

    raise TelegramConfigurationError(
        "Для Telegram требуется @username, ссылка https://t.me/username "
        "или приватный инвайт https://t.me/+hash"
    )


def extract_username(recipient: str) -> str:
    """Backward-compatible helper for callers that only accept public peers."""
    target = parse_telegram_target(recipient)
    if target.kind != "public":
        raise TelegramConfigurationError(
            "Приватная invite-ссылка не содержит публичный username"
        )
    return target.value


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
    return TelegramClient(session, int(api_id), api_hash)


async def _resolve_target(client: TelegramClient, target: TelegramTarget):
    if target.kind == "invite":
        try:
            updates = await client(ImportChatInviteRequest(target.value))
            if not updates.chats:
                raise TelegramSendError(
                    "Telegram принял инвайт, но не вернул группу"
                )
            return updates.chats[0], True
        except UserAlreadyParticipantError:
            invite = await client(CheckChatInviteRequest(target.value))
            chat = getattr(invite, "chat", None)
            if chat is None:
                raise TelegramSendError(
                    "Аккаунт уже состоит в группе, но Telegram не вернул чат"
                )
            return chat, False

    entity = await client.get_entity(target.value)
    if isinstance(entity, User):
        return entity, False

    joined = False
    try:
        await client(JoinChannelRequest(entity))
        joined = True
    except UserAlreadyParticipantError:
        pass
    return entity, joined


class TelegramService:
    @staticmethod
    async def send_message(
        *,
        recipient_external_id: str = "",
        recipient_address: str = "",
        text: str,
    ) -> dict[str, Any]:
        recipient = recipient_address or recipient_external_id
        target = parse_telegram_target(recipient)
        client = build_client()

        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise TelegramSessionExpired(
                    "Пользовательская Telegram-сессия не авторизована"
                )

            entity, joined = await _resolve_target(client, target)
            message = await client.send_message(
                entity,
                text,
                link_preview=False,
            )
            return {
                "success": True,
                "message_id": str(message.id),
                "joined": joined,
                "target_type": (
                    "user" if isinstance(entity, User) else "chat_group"
                ),
            }
        except FloodWaitError as error:
            raise TelegramRequiresHuman(
                "Telegram установил ограничение: повтор возможен через "
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
        except ChatWriteForbiddenError as error:
            raise TelegramSendError(
                "Аккаунт вступил в Telegram-группу, но публикация сообщений "
                "в ней запрещена"
            ) from error
        except ChannelPrivateError as error:
            raise TelegramSendError(
                "Telegram-канал или группа недоступны для аккаунта"
            ) from error
        except (InviteHashInvalidError, InviteHashExpiredError) as error:
            raise TelegramSendError(
                "Приватная Telegram invite-ссылка недействительна или истекла"
            ) from error
        except (UsernameInvalidError, UsernameNotOccupiedError) as error:
            raise TelegramSendError(
                f"Публичный Telegram username @{target.value} не найден"
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
                "Не удалось отправить отчёт о поиске: "
                f"{response.text[:500]}"
            )

    @staticmethod
    async def notify_chat_with_photo(
        chat_id: str,
        text: str,
        photo_path: str,
    ) -> None:
        token = os.getenv("BOT_TOKEN", "").strip()
        path = Path(photo_path)
        if not token or not chat_id.strip():
            raise TelegramConfigurationError(
                "Не заданы BOT_TOKEN или chat_id для уведомления"
            )
        if not path.is_file():
            await TelegramService.notify_chat(
                chat_id,
                f"{text}\n\nСкриншот не найден: {photo_path}",
            )
            return

        async with httpx.AsyncClient(timeout=60) as client:
            with path.open("rb") as photo:
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": text[:1024]},
                    files={
                        "photo": (path.name, photo, "image/png"),
                    },
                )
        if response.is_error:
            # Telegram rejects very wide/tall screenshots as photos. Sending
            # the same image as a document preserves it without dimension
            # restrictions.
            async with httpx.AsyncClient(timeout=60) as client:
                with path.open("rb") as document:
                    document_response = await client.post(
                        f"https://api.telegram.org/bot{token}/sendDocument",
                        data={"chat_id": chat_id, "caption": text[:1024]},
                        files={
                            "document": (
                                path.name,
                                document,
                                "application/octet-stream",
                            ),
                        },
                    )
            if document_response.is_error:
                await TelegramService.notify_chat(
                    chat_id,
                    f"{text}\n\nСкриншот: {photo_path}",
                )

    @staticmethod
    async def notify_operator(text: str) -> None:
        chat_id = os.getenv("OPERATOR_TELEGRAM_CHAT_ID", "").strip()
        if not chat_id:
            raise TelegramConfigurationError(
                "Не задан OPERATOR_TELEGRAM_CHAT_ID для уведомления"
            )
        await TelegramService.notify_chat(chat_id, text)

    @staticmethod
    async def notify_operator_with_photo(
        text: str,
        photo_path: str,
    ) -> None:
        chat_id = os.getenv("OPERATOR_TELEGRAM_CHAT_ID", "").strip()
        if not chat_id:
            raise TelegramConfigurationError(
                "Не задан OPERATOR_TELEGRAM_CHAT_ID для уведомления"
            )
        await TelegramService.notify_chat_with_photo(
            chat_id,
            text,
            photo_path,
        )
