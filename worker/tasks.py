import asyncio
import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from redis import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from config import config
from database.models.communication import Communication
from database.models.contact import Contact
from services.logger import log
from services.mailing_service import ContactMailingError, ContactMailingService
from services.telegram_service import TelegramService
from utils.enums import ContactStatus
from worker.celery_app import celery_app
from worker.policy import is_temporary_error


def _redis() -> Redis:
    return Redis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True,
    )


async def _send(contact_id: int) -> dict[str, str | int]:
    engine = create_async_engine(
        config.database.database_url,
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            claimed_id = await session.scalar(
                update(Contact)
                .where(
                    Contact.id == contact_id,
                    Contact.status.in_(
                        [
                            ContactStatus.APPROVED.value,
                            ContactStatus.QUEUED.value,
                        ]
                    ),
                )
                .values(
                    status=ContactStatus.SENDING.value,
                    next_action="Выполняется отправка",
                    sending_started_at=datetime.now(timezone.utc),
                    delivery_attempts=Contact.delivery_attempts + 1,
                )
                .returning(Contact.id)
            )
            await session.commit()
            if claimed_id is None:
                return {"contact_id": contact_id, "status": "skipped"}

        async with session_factory() as session:
            try:
                communication, message_id = await ContactMailingService(
                    session
                ).send_approved(contact_id)
            except ContactMailingError as error:
                contact = await session.get(Contact, contact_id)
                retryable = is_temporary_error(error)
                if contact and contact.status in {
                    ContactStatus.SENDING.value,
                    ContactStatus.FAILED.value,
                }:
                    contact.status = (
                        ContactStatus.QUEUED.value
                        if retryable
                        else ContactStatus.FAILED.value
                    )
                    contact.next_action = (
                        "Celery повторит временную ошибку"
                        if retryable
                        else "Исправить данные и повторно одобрить"
                    )
                    await session.commit()
                log.warning(
                    "Celery: отправка контакту ID={} завершилась ошибкой: {}",
                    contact_id,
                    error,
                )
                if (
                    contact
                    and contact.status
                    == ContactStatus.REQUIRES_HUMAN.value
                ):
                    await TelegramService.notify_operator(
                        f"VK требует вмешательства для контакта ID={contact_id}.\n"
                        f"{contact.next_action}"
                    )
                return {
                    "contact_id": contact_id,
                    "status": (
                        "requires_human"
                        if contact
                        and contact.status
                        == ContactStatus.REQUIRES_HUMAN.value
                        else "failed"
                    ),
                    "error": str(error),
                    "retryable": retryable,
                }
            except Exception:
                contact = await session.get(Contact, contact_id)
                if contact and contact.status == ContactStatus.SENDING.value:
                    contact.status = ContactStatus.FAILED.value
                    contact.next_action = "Проверить ошибку Celery worker"
                    await session.commit()
                raise
            return {
                "contact_id": contact_id,
                "status": communication.status,
                "channel": communication.channel,
                "message_id": message_id,
            }
    finally:
        await engine.dispose()


async def _delivery_block_reason(contact_id: int) -> str | None:
    timezone_name = os.getenv("MAILING_TIMEZONE", "Asia/Novosibirsk")
    local_now = datetime.now(ZoneInfo(timezone_name))
    start_hour = int(os.getenv("MAILING_WORK_START_HOUR", "9"))
    end_hour = int(os.getenv("MAILING_WORK_END_HOUR", "19"))
    if not start_hour <= local_now.hour < end_hour:
        return "outside_working_hours"
    day_start = datetime.combine(
        local_now.date(),
        time.min,
        tzinfo=ZoneInfo(timezone_name),
    ).astimezone(timezone.utc)
    engine = create_async_engine(
        config.database.database_url,
        poolclass=NullPool,
    )
    try:
        async with async_sessionmaker(engine)() as session:
            channel = await session.scalar(
                select(Contact.preferred_channel).where(
                    Contact.id == contact_id
                )
            )
            channel = (channel or "email").strip().lower()
            count = await session.scalar(
                select(func.count(Communication.id)).where(
                    Communication.direction == "outgoing",
                    Communication.status == "sent",
                    Communication.channel == channel,
                    Communication.created_at >= day_start,
                )
            )
            limit = int(
                os.getenv(
                    f"{channel.upper()}_DAILY_LIMIT",
                    os.getenv("MAILING_DAILY_LIMIT", "50"),
                )
            )
            return "channel_daily_limit" if int(count or 0) >= limit else None
    finally:
        await engine.dispose()


async def _release_stopped_contact(contact_id: int) -> None:
    engine = create_async_engine(
        config.database.database_url,
        poolclass=NullPool,
    )
    try:
        async with async_sessionmaker(engine)() as session:
            await session.execute(
                update(Contact)
                .where(
                    Contact.id == contact_id,
                    Contact.status == ContactStatus.QUEUED.value,
                )
                .values(
                    status=ContactStatus.APPROVED.value,
                    next_action="Рассылка остановлена",
                )
            )
            await session.commit()
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True,
    name="worker.tasks.send_approved_contact",
    max_retries=None,
)
def send_approved_contact(self, contact_id: int):
    state = _redis().get("mailing:state") or "running"
    if state == "stopped":
        asyncio.run(_release_stopped_contact(contact_id))
        return {"contact_id": contact_id, "status": "stopped"}
    if state != "running":
        raise self.retry(countdown=30)

    block_reason = asyncio.run(_delivery_block_reason(contact_id))
    if block_reason:
        raise self.retry(countdown=300)

    result = asyncio.run(_send(contact_id))
    if result.get("retryable"):
        raise self.retry(
            countdown=min(900, 30 * (2 ** self.request.retries)),
            max_retries=3,
        )
    return result


async def _recover_stuck() -> list[tuple[int, str | None]]:
    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=int(os.getenv("MAILING_STUCK_MINUTES", "20"))
    )
    engine = create_async_engine(
        config.database.database_url,
        poolclass=NullPool,
    )
    try:
        async with async_sessionmaker(engine)() as session:
            rows = (
                await session.execute(
                    update(Contact)
                    .where(
                        Contact.status == ContactStatus.SENDING.value,
                        Contact.sending_started_at < cutoff,
                    )
                    .values(
                        status=ContactStatus.APPROVED.value,
                        next_action="Восстановлен после зависшей отправки",
                        sending_started_at=None,
                    )
                    .returning(Contact.id, Contact.preferred_channel)
                )
            ).all()
            await session.commit()
            return [(row[0], row[1]) for row in rows]
    finally:
        await engine.dispose()


@celery_app.task(name="worker.tasks.recover_stuck_contacts")
def recover_stuck_contacts():
    from worker.routing import queue_for_channel

    recovered = asyncio.run(_recover_stuck())
    for contact_id, channel in recovered:
        send_approved_contact.apply_async(
            args=[contact_id],
            queue=queue_for_channel(channel),
        )
    return {"recovered": len(recovered)}
