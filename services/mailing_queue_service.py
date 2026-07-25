import os
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from sqlalchemy import func, select

from database.models.communication import Communication
from database.models.contact import Contact
from database.session import provider
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
            contacts = list(
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
            local_now = datetime.now(self.timezone)
            day_start = datetime.combine(
                local_now.date(),
                time.min,
                tzinfo=self.timezone,
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
            "interval_seconds": self.interval_seconds,
            "daily_limit": self.daily_limit,
            "timezone": str(self.timezone),
            "last_error": None,
            "started_at": started_at,
        }


mailing_queue = MailingQueueController()
