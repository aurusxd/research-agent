from sqlalchemy.ext.asyncio import AsyncSession

from database.session import provider
from database.repositories.contact_repository import ContactRepository
from schemas.save_contact_schema import SaveContactToolArgs
from services.logger import log

@provider.inject_session
async def save_contact(
        organization_name: str,
        source: str,
        relevance_score: int,
        relevance_reason: str,
        session: AsyncSession,
        contact_name: str | None = None,
        position: str | None = None,
        category: str | None = None,
        country: str | None = None,
        region: str | None = None,
        city: str | None = None,
        website: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        vk_url: str | None = None,
        telegram_url: str | None = None,
        youtube_url: str | None = None,
        rutube_url: str | None = None,
        dzen_url: str | None = None,
        preferred_channel: str | None = None,
        generated_message: str | None = None,
    ) -> dict:
    log.info("Зашел в save_contact")
    try:
        data = SaveContactToolArgs(
            organization_name=organization_name,
            contact_name=contact_name,
            position=position,
            category=category,
            country=country,
            region=region,
            city=city,
            website=website,
            email=email,
            phone=phone,
            vk_url=vk_url,
            telegram_url=telegram_url,
            youtube_url=youtube_url,
            rutube_url=rutube_url,
            dzen_url=dzen_url,
            source=source,
            relevance_score=relevance_score,
            relevance_reason=relevance_reason,
            preferred_channel=preferred_channel,
            generated_message=generated_message,
        )

        repository = ContactRepository(session)

        duplicate = await repository.find_duplicate(
            email=data.email,
            website=data.website,
            organization_name=data.organization_name,
            city=data.city,
        )

        if duplicate:
            return {
                "success": True,
                "status": "duplicate",
                "contact_id": duplicate.id,
                "message": "Организация уже существует в базе",
            }

        contact_data = data.model_dump(
            exclude_none=True,
            mode="json",
        )

        contact_data["status"] = "new"

        contact = await repository.create(contact_data)

        return {
            "success": True,
            "status": "created",
            "contact_id": contact.id,
            "message": "Организация сохранена",
        }
    except Exception as e:
        log.exception("Ошибка сохранения")
        return {
            "success": False,
            "status": "error",
            "message": "Ошибка сохранения",
        }