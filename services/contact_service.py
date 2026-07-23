from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.contact import Contact
from database.repositories.contact_repository import ContactRepository
from schemas.contact import ContactCreate, ContactUpdate
from schemas.save_contact_schema import SaveContactToolArgs, SaveContactToolResult
from utils.exceptions import (
    ContactAlreadyExistsError,
    ContactNotFoundError,
)
from database.session import provider


class ContactService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ContactRepository(session)

    async def get_by_id(self, contact_id: int) -> Contact:
        contact = await self.repository.get_by_id(contact_id)

        if contact is None:
            raise ContactNotFoundError(
                f"Контакт с ID {contact_id} не найден"
            )

        return contact

    async def get_with_communications(
        self,
        contact_id: int,
    ) -> Contact:
        contact = await self.repository.get_with_communications(
            contact_id
        )

        if contact is None:
            raise ContactNotFoundError(
                f"Контакт с ID {contact_id} не найден"
            )

        return contact

    async def create(self, data: ContactCreate) -> Contact:
        duplicate = await self.repository.find_duplicate(
            email=str(data.email) if data.email else None,
            website=data.website,
            organization_name=data.organization_name,
            city=data.city,
        )

        if duplicate is not None:
            raise ContactAlreadyExistsError(
                f"Похожий контакт уже существует: ID {duplicate.id}"
            )

        try:
            contact = await self.repository.create(
                data.model_dump(
                    exclude_none=True,
                    mode="json",
                )
            )
            await self.session.commit()

            return contact

        except IntegrityError as error:
            await self.session.rollback()

            raise ContactAlreadyExistsError(
                "Контакт с такими данными уже существует"
            ) from error

        except Exception:
            await self.session.rollback()
            raise

    async def update(
        self,
        contact_id: int,
        data: ContactUpdate,
    ) -> Contact:
        contact = await self.get_by_id(contact_id)

        update_data = data.model_dump(
            exclude_unset=True,
            mode="json",
        )

        if not update_data:
            return contact

        try:
            contact = await self.repository.update(
                contact,
                update_data,
            )
            await self.session.commit()

            return contact

        except Exception:
            await self.session.rollback()
            raise

    async def delete(self, contact_id: int) -> None:
        contact = await self.get_by_id(contact_id)

        try:
            await self.repository.delete(contact)
            await self.session.commit()

        except Exception:
            await self.session.rollback()
            raise

    async def search(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        city: str | None = None,
        region: str | None = None,
        status: str | None = None,
        min_relevance: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Contact]:
        return await self.repository.search(
            query=query,
            category=category,
            city=city,
            region=region,
            status=status,
            min_relevance=min_relevance,
            limit=limit,
            offset=offset,
        )

    async def change_status(
        self,
        contact_id: int,
        status: str,
    ) -> Contact:
        allowed_statuses = {
            "new",
            "approved",
            "contacted",
            "waiting_response",
            "responded",
            "interested",
            "rejected",
            "follow_up",
            "blocked",
        }

        if status not in allowed_statuses:
            raise ValueError(
                f"Недопустимый статус: {status}"
            )

        return await self.update(
            contact_id,
            ContactUpdate(status=status),
        )

    async def save_generated_message(
        self,
        contact_id: int,
        message: str,
    ) -> Contact:
        return await self.update(
            contact_id,
            ContactUpdate(
                generated_message=message,
                status="approved",
            ),
        )
    
