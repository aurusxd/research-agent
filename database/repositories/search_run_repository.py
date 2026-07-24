from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Contact, SearchRun


class SearchRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: dict[str, Any]) -> SearchRun:
        search_run = SearchRun(**data)
        self.session.add(search_run)
        await self.session.flush()
        await self.session.refresh(search_run)
        return search_run

    async def get_by_id(self, search_run_id: int) -> SearchRun | None:
        return await self.session.get(SearchRun, search_run_id)

    async def get_with_contacts(self, search_run_id: int) -> SearchRun | None:
        statement = (
            select(SearchRun)
            .options(selectinload(SearchRun.contacts))
            .where(SearchRun.id == search_run_id)
        )
        return await self.session.scalar(statement)

    async def get_all(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SearchRun]:
        statement = (
            select(SearchRun)
            .order_by(SearchRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def count_contacts(self, search_run_id: int) -> int:
        statement = select(func.count(Contact.id)).where(
            Contact.search_run_id == search_run_id
        )
        return await self.session.scalar(statement) or 0
