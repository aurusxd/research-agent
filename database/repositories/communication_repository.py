from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database.models.communication import Communication


class CommunicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        communication_id: int,
    ) -> Communication | None:
        return await self.session.get(
            Communication,
            communication_id,
        )

    async def get_with_contact(
        self,
        communication_id: int,
    ) -> Communication | None:
        statement = (
            select(Communication)
            .options(joinedload(Communication.contact))
            .where(Communication.id == communication_id)
        )

        return await self.session.scalar(statement)

    async def get_all(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Communication]:
        statement = (
            select(Communication)
            .order_by(Communication.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.scalars(statement)
        return list(result.all())

    async def get_by_contact_id(
        self,
        contact_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Communication]:
        statement = (
            select(Communication)
            .where(Communication.contact_id == contact_id)
            .order_by(Communication.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.scalars(statement)
        return list(result.all())

    async def get_last_by_contact_id(
        self,
        contact_id: int,
    ) -> Communication | None:
        statement = (
            select(Communication)
            .where(Communication.contact_id == contact_id)
            .order_by(Communication.created_at.desc())
            .limit(1)
        )

        return await self.session.scalar(statement)

    async def create(
        self,
        data: dict[str, Any],
    ) -> Communication:
        communication = Communication(**data)

        self.session.add(communication)
        await self.session.flush()
        await self.session.refresh(communication)

        return communication

    async def update(
        self,
        communication: Communication,
        data: dict[str, Any],
    ) -> Communication:
        for field, value in data.items():
            if not hasattr(communication, field):
                raise ValueError(
                    f"У модели Communication нет поля {field!r}"
                )

            setattr(communication, field, value)

        await self.session.flush()
        await self.session.refresh(communication)

        return communication

    async def delete(
        self,
        communication: Communication,
    ) -> None:
        await self.session.delete(communication)
        await self.session.flush()

    async def get_by_status(
        self,
        status: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Communication]:
        statement = (
            select(Communication)
            .where(Communication.status == status)
            .order_by(Communication.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.scalars(statement)
        return list(result.all())

    async def get_unsent(
        self,
        *,
        limit: int = 100,
    ) -> list[Communication]:
        statement = (
            select(Communication)
            .where(
                Communication.direction == "outgoing",
                Communication.status.in_(
                    ["created", "pending", "failed"]
                ),
            )
            .order_by(Communication.created_at.asc())
            .limit(limit)
        )

        result = await self.session.scalars(statement)
        return list(result.all())

    async def count_by_contact_id(
        self,
        contact_id: int,
    ) -> int:
        statement = select(
            func.count(Communication.id)
        ).where(
            Communication.contact_id == contact_id
        )

        return await self.session.scalar(statement) or 0