import asyncio
import os
from datetime import datetime, time, timezone
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
from utils.enums import ContactStatus
from worker.celery_app import celery_app


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
                if contact and contact.status == ContactStatus.SENDING.value:
                    contact.status = ContactStatus.FAILED.value
                    contact.next_action = "Исправить данные и повторно одобрить"
                    await session.commit()
                log.warning(
                    "Celery: отправка контакту ID={} завершилась ошибкой: {}",
                    contact_id,
                    error,
                )
                return {
                    "contact_id": contact_id,
                    "status": "failed",
                    "error": str(error),
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
                "status": "sent",
                "channel": communication.channel,
                "message_id": message_id,
            }
    finally:
        await engine.dispose()


async def _daily_limit_reached() -> bool:
    timezone_name = os.getenv("MAILING_TIMEZONE", "Asia/Novosibirsk")
    local_now = datetime.now(ZoneInfo(timezone_name))
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
            count = await session.scalar(
                select(func.count(Communication.id)).where(
                    Communication.direction == "outgoing",
                    Communication.status == "sent",
                    Communication.created_at >= day_start,
                )
            )
            return int(count or 0) >= int(
                os.getenv("MAILING_DAILY_LIMIT", "50")
            )
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

    if asyncio.run(_daily_limit_reached()):
        _redis().set("mailing:state", "limit_reached")
        raise self.retry(countdown=300)

    return asyncio.run(_send(contact_id))
