import asyncio
import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from redis import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from config import config
from database.session import provider
from database.models.communication import Communication
from database.models.contact import Contact
from services.logger import log
from services.mailing_service import ContactMailingError, ContactMailingService
from services.search_run_service import SearchRunService
from services.telegram_service import TelegramService
from utils.enums import ContactStatus
from worker.celery_app import celery_app
from worker.policy import is_temporary_error
from worker.routing import queue_for_channel


def _redis() -> Redis:
    return Redis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True,
    )


def _build_search_report(result: dict[str, str | int]) -> str:
    status = str(result["status"])
    status_label = {
        "completed": "завершён",
        "partially_completed": "завершён с отдельными ошибками",
        "failed": "завершился ошибкой",
    }.get(status, status)
    lines = [
        f"🔎 Поиск #{result['search_run_id']} {status_label}.",
        f"Найдено уникальных результатов: {result['found_count']}",
        f"Сохранено контактов: {result['saved_count']}",
        f"Исключено дублей: {result['duplicate_count']}",
        f"Ошибок: {result['error_count']}",
    ]
    error_message = str(result.get("error_message") or "").strip()
    if error_message:
        lines.append(f"Причина: {error_message[:700]}")
    if int(result["saved_count"]) > 0:
        lines.append("Контакты доступны в разделе «Проверка материалов».")
    return "\n".join(lines)


async def _execute_search(
    search_run_id: int,
    notification_chat_id: str | None = None,
) -> dict[str, str | int]:
    # Provider is module-global, while every Celery task gets a fresh loop via
    # asyncio.run(). Never reuse asyncpg connections created by an older loop.
    await provider.engine.dispose(close=False)
    engine = create_async_engine(
        config.database.database_url,
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            search_run = await SearchRunService(session).execute(search_run_id)
            result = {
                "search_run_id": search_run.id,
                "status": search_run.status,
                "found_count": search_run.found_count,
                "saved_count": search_run.saved_count,
                "duplicate_count": search_run.duplicate_count,
                "error_count": search_run.error_count,
                "error_message": search_run.error_message or "",
            }
            if notification_chat_id:
                try:
                    await TelegramService.notify_chat(
                        notification_chat_id,
                        _build_search_report(result),
                    )
                except Exception:
                    log.exception(
                        "Не удалось уведомить Telegram о завершении поиска ID={}",
                        search_run_id,
                    )
            return result
    finally:
        await provider.engine.dispose()
        await engine.dispose()


@celery_app.task(
    name="worker.tasks.execute_search_run",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def execute_search_run(
    search_run_id: int,
    notification_chat_id: str | None = None,
):
    return asyncio.run(_execute_search(search_run_id, notification_chat_id))


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
                            ContactStatus.DRY_RUN.value,
                            ContactStatus.FAILED.value,
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
                if (
                    contact
                    and contact.preferred_channel == "contact_form"
                    and contact.email
                    and contact.status != ContactStatus.REQUIRES_HUMAN.value
                ):
                    contact.preferred_channel = "email"
                    contact.recipient_address = contact.email
                    contact.status = ContactStatus.QUEUED.value
                    contact.next_action = (
                        "Форма не отправилась; автоматический fallback на email"
                    )
                    await session.commit()
                    return {
                        "contact_id": contact_id,
                        "status": "fallback",
                        "fallback_channel": "email",
                        "error": str(error),
                    }
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
                        f"Канал требует вмешательства для контакта ID={contact_id}.\n"
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


async def _mark_retry_exhausted(contact_id: int, error: str) -> None:
    engine = create_async_engine(
        config.database.database_url,
        poolclass=NullPool,
    )
    try:
        async with async_sessionmaker(engine)() as session:
            await session.execute(
                update(Contact)
                .where(Contact.id == contact_id)
                .values(
                    status=ContactStatus.FAILED.value,
                    next_action=(
                        "Автоматические повторы исчерпаны: "
                        f"{error[:500]}"
                    ),
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
    fallback_channel = result.get("fallback_channel")
    if isinstance(fallback_channel, str):
        send_approved_contact.apply_async(
            args=[contact_id],
            queue=queue_for_channel(fallback_channel),
        )
        return result
    if result.get("retryable"):
        if self.request.retries >= 3:
            asyncio.run(
                _mark_retry_exhausted(
                    contact_id,
                    str(result.get("error") or "временная ошибка"),
                )
            )
            return {
                **result,
                "status": "failed",
                "retry_exhausted": True,
            }
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
    recovered = asyncio.run(_recover_stuck())
    for contact_id, channel in recovered:
        send_approved_contact.apply_async(
            args=[contact_id],
            queue=queue_for_channel(channel),
        )
    return {"recovered": len(recovered)}
