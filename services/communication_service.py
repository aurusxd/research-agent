from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from database.models.communication import Communication
from database.repositories.communication_repository import (
    CommunicationRepository,
)
from database.repositories.contact_repository import ContactRepository
from schemas.communication import (
    CommunicationCreate,
    CommunicationUpdate,
)
from utils.exceptions import (
    CommunicationNotFoundError,
    ContactNotFoundError,
)


class CommunicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = CommunicationRepository(session)
        self.contact_repository = ContactRepository(session)

    async def get_by_id(
        self,
        communication_id: int,
    ) -> Communication:
        communication = await self.repository.get_by_id(
            communication_id
        )

        if communication is None:
            raise CommunicationNotFoundError(
                f"Коммуникация с ID "
                f"{communication_id} не найдена"
            )

        return communication

    async def create(
        self,
        data: CommunicationCreate,
    ) -> Communication:
        contact = await self.contact_repository.get_by_id(
            data.contact_id
        )

        if contact is None:
            raise ContactNotFoundError(
                f"Контакт с ID {data.contact_id} не найден"
            )

        try:
            communication = await self.repository.create(
                data.model_dump()
            )

            now = datetime.now(timezone.utc)
            contact.last_contact_at = now

            if data.direction == "outgoing":
                contact.status = "contacted"
                contact.preferred_channel = data.channel
            else:
                contact.status = "responded"
                contact.response = data.message

            await self.session.flush()
            await self.session.commit()

            return communication

        except Exception:
            await self.session.rollback()
            raise

    async def register_outgoing(
        self,
        *,
        contact_id: int,
        channel: str,
        message: str,
        status: str = "sent",
    ) -> Communication:
        return await self.create(
            CommunicationCreate(
                contact_id=contact_id,
                channel=channel,
                direction="outgoing",
                message=message,
                status=status,
            )
        )

    async def register_incoming(
        self,
        *,
        contact_id: int,
        channel: str,
        message: str,
    ) -> Communication:
        return await self.create(
            CommunicationCreate(
                contact_id=contact_id,
                channel=channel,
                direction="incoming",
                message=message,
                status="received",
            )
        )

    async def update(
        self,
        communication_id: int,
        data: CommunicationUpdate,
    ) -> Communication:
        communication = await self.get_by_id(
            communication_id
        )

        update_data = data.model_dump(exclude_unset=True)

        if not update_data:
            return communication

        try:
            communication = await self.repository.update(
                communication,
                update_data,
            )
            await self.session.commit()

            return communication

        except Exception:
            await self.session.rollback()
            raise

    async def get_contact_history(
        self,
        contact_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Communication]:
        contact = await self.contact_repository.get_by_id(
            contact_id
        )

        if contact is None:
            raise ContactNotFoundError(
                f"Контакт с ID {contact_id} не найден"
            )

        return await self.repository.get_by_contact_id(
            contact_id,
            limit=limit,
            offset=offset,
        )

    async def delete(
        self,
        communication_id: int,
    ) -> None:
        communication = await self.get_by_id(
            communication_id
        )

        try:
            await self.repository.delete(communication)
            await self.session.commit()

        except Exception:
            await self.session.rollback()
            raise