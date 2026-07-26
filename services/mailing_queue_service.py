import os
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from sqlalchemy import func, select

from database.models.communication import Communication
from database.models.contact import Contact
from database.session import provider
from services.invitation_generator import ensure_contact_invitation
from utils.enums import ContactStatus
from worker.routing import queue_for_channel


class MailingQueueController:
    """Controls durable Celery queues through Redis."""

    def __init__(self) -> None:
        self.redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

    @property
    def interval_seconds(self) -> int:
        return max(1, int(os.getenv("MAILING_INTERVAL_SECONDS", "30")))

    @property
    def daily_limit(self) -> int:
        return max(1, int(os.getenv("MAILING_DAILY_LIMIT", "50")))

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(os.getenv("MAILING_TIMEZONE", "Asia/Novosibirsk"))

    async def _redis(self) -> Redis:
        return Redis.from_url(self.redis_url, decode_responses=True)

    async def enqueue_contact(
        self,
        contact_id: int,
        preferred_channel: str | None,
    ) -> str:
        channel = (preferred_channel or "email").strip().lower()
        queue = queue_for_channel(channel)
        from worker.tasks import send_approved_contact

        task = send_approved_contact.apply_async(args=[contact_id], queue=queue)
        async with provider.session_factory() as session:
            contact = await session.get(Contact, contact_id)
            if contact:
                contact.celery_task_id = task.id
                if contact.status == ContactStatus.APPROVED.value:
                    contact.status = ContactStatus.QUEUED.value
                    contact.next_action = f"В очереди {channel}"
                await session.commit()
        return queue

    async def start(self) -> dict[str, Any]:
        redis = await self._redis()
        try:
            await redis.set("mailing:state", "running")
            await redis.set("mailing:started_at", datetime.now(timezone.utc).isoformat())
        finally:
            await redis.aclose()

        async with provider.session_factory() as session:
            candidates = list(
                (
                    await session.scalars(
                        select(Contact).where(
                            Contact.status.in_(
                                [
                                    ContactStatus.APPROVED.value,
                                    ContactStatus.QUEUED.value,
                                    ContactStatus.DRY_RUN.value,
                                    ContactStatus.FAILED.value,
                                ]
                            )
                        )
                    )
                ).all()
            )
            contacts = []
            for contact in candidates:
                if not (contact.generated_message or "").strip():
                    contact.generated_message = ensure_contact_invitation(contact)
                    contact.status = ContactStatus.PENDING_REVIEW.value
                    contact.next_action = (
                        "Черновик восстановлен автоматически — требуется проверка"
                    )
                    continue
                if contact.status == ContactStatus.FAILED.value:
                    # Temporary failures are retried by the original Celery
                    # task. A new mailing run must not revive exhausted or
                    # permanent failures and create duplicate deliveries.
                    continue
                contacts.append(contact)
            await session.commit()
        for contact in contacts:
            await self.enqueue_contact(contact.id, contact.preferred_channel)
        return await self.status()

    async def pause(self) -> dict[str, Any]:
        await self._set_state("paused")
        return await self.status()

    async def resume(self) -> dict[str, Any]:
        return await self.start()

    async def stop(self) -> dict[str, Any]:
        await self._set_state("stopped")
        return await self.status()

    async def _set_state(self, state: str) -> None:
        redis = await self._redis()
        try:
            await redis.set("mailing:state", state)
        finally:
            await redis.aclose()

    async def status(self) -> dict[str, Any]:
        redis = await self._redis()
        try:
            state = await redis.get("mailing:state") or "running"
            started_at = await redis.get("mailing:started_at")
            scheduled_at = await redis.get("mailing:scheduled_at")
            settings = await self._settings_from_redis(redis)
        finally:
            await redis.aclose()

        async with provider.session_factory() as session:
            pending = await session.scalar(
                select(func.count(Contact.id)).where(
                    Contact.status.in_(
                        [
                            ContactStatus.APPROVED.value,
                            ContactStatus.QUEUED.value,
                            ContactStatus.SENDING.value,
                            ContactStatus.DRY_RUN.value,
                        ]
                    )
                )
            )
            active_timezone = ZoneInfo(settings["timezone"])
            local_now = datetime.now(active_timezone)
            day_start = datetime.combine(
                local_now.date(),
                time.min,
                tzinfo=active_timezone,
            ).astimezone(timezone.utc)
            run_start = None
            if started_at:
                try:
                    run_start = datetime.fromisoformat(started_at)
                except ValueError:
                    run_start = None
            sent_today = await session.scalar(
                select(func.count(Communication.id)).where(
                    Communication.direction == "outgoing",
                    Communication.status == "sent",
                    Communication.created_at >= day_start,
                )
            )
            failed_today = await session.scalar(
                select(func.count(Communication.id)).where(
                    Communication.direction == "outgoing",
                    Communication.status == "failed",
                    Communication.created_at >= day_start,
                )
            )
            sent_in_run = 0
            failed_in_run = 0
            if run_start is not None:
                sent_in_run = await session.scalar(
                    select(func.count(Communication.id)).where(
                        Communication.direction == "outgoing",
                        Communication.status == "sent",
                        Communication.created_at >= run_start,
                    )
                )
                failed_in_run = await session.scalar(
                    select(func.count(Communication.id)).where(
                        Communication.direction == "outgoing",
                        Communication.status == "failed",
                        Communication.created_at >= run_start,
                    )
                )
        return {
            "state": state,
            "approved_pending": int(pending or 0),
            "sent_in_run": int(sent_in_run or 0),
            "sent_today": int(sent_today or 0),
            "failed_in_run": int(failed_in_run or 0),
            "interval_seconds": settings["interval_seconds"],
            "daily_limit": settings["daily_limit"],
            "timezone": settings["timezone"],
            "work_start_hour": settings["work_start_hour"],
            "work_end_hour": settings["work_end_hour"],
            "last_error": None,
            "started_at": started_at,
            "scheduled_at": scheduled_at,
        }

    async def _settings_from_redis(self, redis: Redis) -> dict[str, Any]:
        values = await redis.mget(
            "settings:interval_seconds",
            "settings:daily_limit",
            "settings:timezone",
            "settings:work_start_hour",
            "settings:work_end_hour",
        )
        return {
            "interval_seconds": int(values[0] or self.interval_seconds),
            "daily_limit": int(values[1] or self.daily_limit),
            "timezone": values[2] or str(self.timezone),
            "work_start_hour": int(
                values[3] or os.getenv("MAILING_WORK_START_HOUR", "9")
            ),
            "work_end_hour": int(
                values[4] or os.getenv("MAILING_WORK_END_HOUR", "19")
            ),
        }

    async def get_settings(self) -> dict[str, Any]:
        redis = await self._redis()
        try:
            return await self._settings_from_redis(redis)
        finally:
            await redis.aclose()

    async def update_settings(
        self,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        redis = await self._redis()
        try:
            mapping = {
                f"settings:{key}": str(value)
                for key, value in values.items()
            }
            if mapping:
                await redis.mset(mapping)
            return await self._settings_from_redis(redis)
        finally:
            await redis.aclose()

    async def schedule(self, scheduled_at: datetime) -> dict[str, Any]:
        if scheduled_at.tzinfo is None:
            raise ValueError("Дата запуска должна содержать часовой пояс")
        if scheduled_at <= datetime.now(timezone.utc):
            raise ValueError("Дата запуска должна быть в будущем")

        from worker.tasks import start_scheduled_mailing

        task = start_scheduled_mailing.apply_async(eta=scheduled_at)
        redis = await self._redis()
        try:
            previous_task_id = await redis.get("mailing:scheduled_task_id")
            if previous_task_id:
                from worker.celery_app import celery_app

                celery_app.control.revoke(previous_task_id)
            await redis.mset(
                {
                    "mailing:state": "scheduled",
                    "mailing:scheduled_at": scheduled_at.isoformat(),
                    "mailing:scheduled_task_id": task.id,
                }
            )
        finally:
            await redis.aclose()
        return await self.status()


mailing_queue = MailingQueueController()
