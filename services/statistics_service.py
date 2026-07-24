from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Communication, SearchRun
from database.repositories.contact_repository import ContactRepository
from schemas.statistics import StatisticsRead
from utils.enums import CommunicationStatus, ContactStatus, SearchRunStatus


StatisticsPeriod = Literal["today", "week", "all"]
NOVOSIBIRSK = ZoneInfo("Asia/Novosibirsk")


class StatisticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.contact_repository = ContactRepository(session)

    async def get(self, period: StatisticsPeriod) -> StatisticsRead:
        since = self._period_start(period)
        statuses = await self.contact_repository.count_by_status(
            since=since
        )
        contacts_found = await self.contact_repository.count(since=since)

        search_statement = select(
            func.count(SearchRun.id),
            func.coalesce(func.sum(SearchRun.found_count), 0),
            func.coalesce(func.sum(SearchRun.error_count), 0),
        )
        if since is not None:
            search_statement = search_statement.where(
                SearchRun.created_at >= since
            )
        search_runs, pages_found, search_errors = (
            await self.session.execute(search_statement)
        ).one()

        communication_statement = select(
            Communication.status,
            func.count(Communication.id),
        ).group_by(Communication.status)
        if since is not None:
            communication_statement = communication_statement.where(
                Communication.created_at >= since
            )
        communication_rows = await self.session.execute(
            communication_statement
        )
        communications = dict(communication_rows.all())

        failed_runs_statement = select(
            func.count(SearchRun.id)
        ).where(SearchRun.status == SearchRunStatus.FAILED.value)
        if since is not None:
            failed_runs_statement = failed_runs_statement.where(
                SearchRun.created_at >= since
            )
        failed_runs = (
            await self.session.scalar(failed_runs_statement) or 0
        )

        return StatisticsRead(
            period=period,
            search_runs=int(search_runs or 0),
            pages_found=int(pages_found or 0),
            contacts_found=contacts_found,
            pending_review=statuses.get(
                ContactStatus.PENDING_REVIEW.value,
                0,
            ),
            approved=statuses.get(ContactStatus.APPROVED.value, 0),
            rejected=statuses.get(ContactStatus.REJECTED.value, 0),
            emails_sent=communications.get(
                CommunicationStatus.SENT.value,
                0,
            ),
            replies=statuses.get(ContactStatus.REPLIED.value, 0),
            errors=(
                int(search_errors or 0)
                + failed_runs
                + communications.get(
                    CommunicationStatus.FAILED.value,
                    0,
                )
            ),
        )

    @staticmethod
    def _period_start(
        period: StatisticsPeriod,
    ) -> datetime | None:
        now = datetime.now(timezone.utc)
        if period == "all":
            return None
        if period == "week":
            return now - timedelta(days=7)

        local_now = now.astimezone(NOVOSIBIRSK)
        local_start = local_now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        return local_start.astimezone(timezone.utc)
