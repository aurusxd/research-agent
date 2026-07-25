import asyncio
import os
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from database.session import provider
from services.logger import log
from services.mailing_service import ContactMailingError, ContactMailingService
from database.repositories.contact_repository import ContactRepository
from database.models.communication import Communication
from database.models.contact import Contact
from sqlalchemy import func, select
from utils.enums import ContactStatus


class MailingQueueController:
    """Runs one sequential email sender for all operator-approved contacts."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._wake_up = asyncio.Event()
        self._state = "stopped"
        self._sent_in_run = 0
        self._failed_in_run = 0
        self._last_error: str | None = None
        self._started_at: datetime | None = None

    @property
    def interval_seconds(self) -> int:
        return max(1, int(os.getenv("MAILING_INTERVAL_SECONDS", "30")))

    @property
    def daily_limit(self) -> int:
        return max(1, int(os.getenv("MAILING_DAILY_LIMIT", "50")))

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(os.getenv("MAILING_TIMEZONE", "Asia/Novosibirsk"))

    async def start(self) -> dict[str, Any]:
        if self._task is not None and not self._task.done():
            self._state = "running"
            self._wake_up.set()
            return await self.status()

        self._state = "running"
        self._sent_in_run = 0
        self._failed_in_run = 0
        self._last_error = None
        self._started_at = datetime.now(timezone.utc)
        self._wake_up.set()
        self._task = asyncio.create_task(
            self._run(),
            name="approved-email-mailing-queue",
        )
        return await self.status()

    async def pause(self) -> dict[str, Any]:
        if self._task is not None and not self._task.done():
            self._state = "paused"
            self._wake_up.clear()
        return await self.status()

    async def resume(self) -> dict[str, Any]:
        return await self.start()

    async def stop(self) -> dict[str, Any]:
        self._state = "stopped"
        self._wake_up.set()
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None
        return await self.status()

    async def status(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "approved_pending": await self._count_approved(),
            "sent_in_run": self._sent_in_run,
            "sent_today": await self._sent_today(),
            "failed_in_run": self._failed_in_run,
            "interval_seconds": self.interval_seconds,
            "daily_limit": self.daily_limit,
            "timezone": str(self.timezone),
            "last_error": self._last_error,
            "started_at": (
                self._started_at.isoformat()
                if self._started_at is not None
                else None
            ),
        }

    async def _count_approved(self) -> int:
        async with provider.session_factory() as session:
            statement = select(func.count(Contact.id)).where(
                Contact.status == ContactStatus.APPROVED.value,
            )
            return int(await session.scalar(statement) or 0)

    async def _sent_today(self) -> int:
        local_now = datetime.now(self.timezone)
        today_start = datetime.combine(
            local_now.date(),
            time.min,
            tzinfo=self.timezone,
        ).astimezone(timezone.utc)
        async with provider.session_factory() as session:
            statement = select(func.count(Communication.id)).where(
                Communication.direction == "outgoing",
                Communication.channel == "email",
                Communication.status == "sent",
                Communication.created_at >= today_start,
            )
            return int(await session.scalar(statement) or 0)

    async def _next_approved_contact_id(self) -> int | None:
        async with provider.session_factory() as session:
            contacts = await ContactRepository(session).search(
                status=ContactStatus.APPROVED.value,
                limit=1,
            )
            return contacts[0].id if contacts else None

    async def _run(self) -> None:
        try:
            while self._state != "stopped":
                await self._wake_up.wait()
                if self._state != "running":
                    continue
                if await self._sent_today() >= self.daily_limit:
                    self._state = "limit_reached"
                    self._wake_up.clear()
                    continue

                contact_id = await self._next_approved_contact_id()
                if contact_id is None:
                    await asyncio.sleep(self.interval_seconds)
                    continue

                try:
                    async with provider.session_factory() as session:
                        await ContactMailingService(
                            session
                        ).send_approved(contact_id)
                    self._sent_in_run += 1
                    self._last_error = None
                except ContactMailingError as error:
                    self._failed_in_run += 1
                    self._last_error = str(error)
                    log.warning(
                        "Авторассылка: контакт ID={} не отправлен: {}",
                        contact_id,
                        error,
                    )
                except Exception as error:  # noqa: BLE001
                    self._failed_in_run += 1
                    self._last_error = str(error)
                    log.exception(
                        "Авторассылка: неожиданная ошибка для ID={}",
                        contact_id,
                    )

                if self._state == "running":
                    await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            raise
        finally:
            if self._state not in {"stopped", "limit_reached", "idle"}:
                self._state = "stopped"


mailing_queue = MailingQueueController()
