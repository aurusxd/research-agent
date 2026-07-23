from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models.contact import Contact


class ContactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, contact_id: int) -> Contact | None:
        return await self.session.get(Contact, contact_id)

    async def get_with_communications(
        self,
        contact_id: int,
    ) -> Contact | None:
        statement = (
            select(Contact)
            .options(selectinload(Contact.communications))
            .where(Contact.id == contact_id)
        )

        return await self.session.scalar(statement)

    async def get_all(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Contact]:
        statement = (
            select(Contact)
            .order_by(Contact.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.scalars(statement)
        return list(result.all())

    async def get_by_email(self, email: str) -> Contact | None:
        normalized_email = email.strip().lower()

        statement = select(Contact).where(
            func.lower(Contact.email) == normalized_email
        )

        return await self.session.scalar(statement)

    async def get_by_website(
        self,
        website: str,
    ) -> Contact | None:
        normalized_website = website.strip().lower()

        statement = select(Contact).where(
            func.lower(Contact.website) == normalized_website
        )

        return await self.session.scalar(statement)

    async def create(
        self,
        data: dict[str, Any],
    ) -> Contact:
        contact = Contact(**data)

        self.session.add(contact)
        await self.session.flush()
        await self.session.refresh(contact)

        return contact

    async def update(
        self,
        contact: Contact,
        data: dict[str, Any],
    ) -> Contact:
        for field, value in data.items():
            if not hasattr(contact, field):
                raise ValueError(
                    f"У модели Contact нет поля {field!r}"
                )

            setattr(contact, field, value)

        await self.session.flush()
        await self.session.refresh(contact)

        return contact

    async def delete(
        self,
        contact: Contact,
    ) -> None:
        await self.session.delete(contact)
        await self.session.flush()

    async def find_duplicate(
        self,
        *,
        email: str | None = None,
        website: str | None = None,
        organization_name: str | None = None,
        city: str | None = None,
    ) -> Contact | None:
        conditions = []

        if email:
            conditions.append(
                func.lower(Contact.email)
                == email.strip().lower()
            )

        if website:
            conditions.append(
                func.lower(Contact.website)
                == website.strip().lower()
            )

        if organization_name and city:
            conditions.append(
                (
                    func.lower(Contact.organization_name)
                    == organization_name.strip().lower()
                )
                & (
                    func.lower(Contact.city)
                    == city.strip().lower()
                )
            )

        if not conditions:
            return None

        statement = select(Contact).where(or_(*conditions))

        return await self.session.scalar(statement)

    async def search(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        country: str | None = None,
        region: str | None = None,
        city: str | None = None,
        status: str | None = None,
        min_relevance_score: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Contact]:
        statement = select(Contact)

        if query:
            search_value = f"%{query.strip()}%"

            statement = statement.where(
                or_(
                    Contact.organization_name.ilike(search_value),
                    Contact.contact_name.ilike(search_value),
                    Contact.email.ilike(search_value),
                    Contact.website.ilike(search_value),
                )
            )

        if category:
            statement = statement.where(
                Contact.category == category
            )

        if country:
            statement = statement.where(
                func.lower(Contact.country)
                == country.strip().lower()
            )

        if region:
            statement = statement.where(
                func.lower(Contact.region)
                == region.strip().lower()
            )

        if city:
            statement = statement.where(
                func.lower(Contact.city)
                == city.strip().lower()
            )

        if status:
            statement = statement.where(
                Contact.status == status
            )

        if min_relevance_score is not None:
            statement = statement.where(
                Contact.relevance_score >= min_relevance_score
            )

        statement = (
            statement
            .order_by(
                Contact.relevance_score.desc(),
                Contact.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.scalars(statement)
        return list(result.all())

    async def count(self) -> int:
        statement = select(func.count(Contact.id))

        return await self.session.scalar(statement) or 0

    async def count_by_status(self) -> dict[str, int]:
        statement = (
            select(
                Contact.status,
                func.count(Contact.id),
            )
            .group_by(Contact.status)
        )

        result = await self.session.execute(statement)

        return {
            status: count
            for status, count in result.all()
        }