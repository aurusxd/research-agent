import asyncio
import os
import re

from sqlalchemy.ext.asyncio import AsyncSession

from database.session import provider
from database.repositories.contact_repository import ContactRepository
from schemas.save_contact_schema import SaveContactToolArgs
from services.logger import log
from services.invitation_generator import ensure_invitation
from utils.enums import ContactStatus
from services.source_verification import verify_source

@provider.inject_session
async def save_contact(
        organization_name: str,
        source: str,
        relevance_score: int,
        relevance_reason: str,
        session: AsyncSession,
        search_run_id: int | None = None,
        contact_name: str | None = None,
        position: str | None = None,
        category: str | None = None,
        country: str | None = None,
        region: str | None = None,
        city: str | None = None,
        website: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        contact_form_url: str | None = None,
        vk_url: str | None = None,
        telegram_url: str | None = None,
        ok_url: str | None = None,
        youtube_url: str | None = None,
        rutube_url: str | None = None,
        dzen_url: str | None = None,
        preferred_channel: str | None = None,
        generated_message: str | None = None,
        recipient_address: str | None = None,
        recipient_external_id: str | None = None,
    ) -> dict:
    log.info("Зашел в save_contact")
    try:
        source_urls = [
            item.rstrip(".,;)")
            for item in re.findall(r"https?://\S+", source)
        ][:5]
        if (
            os.getenv(
                "CONTACT_SOURCE_VERIFICATION_REQUIRED",
                "true",
            ).lower()
            == "true"
        ):
            if not source_urls:
                raise ValueError("Не указан URL первоисточника")
            verifications = await asyncio.gather(
                *[
                    asyncio.to_thread(verify_source, url)
                    for url in source_urls
                ]
            )
            verified_sources = [
                item for item in verifications if item.get("verified")
            ]
            if not verified_sources:
                log.warning(
                    "Первоисточники недоступны для автоматической проверки; "
                    "контакт {} будет сохранён без email",
                    organization_name,
                )
                if email and recipient_address and (
                    recipient_address.strip().lower()
                    == email.strip().lower()
                ):
                    recipient_address = None
                email = None
                if (preferred_channel or "").strip().lower() == "email":
                    preferred_channel = None
            verified_emails = {
                item.strip().lower()
                for verification in verified_sources
                for item in verification.get("emails") or []
            }
            if email and email.strip().lower() not in verified_emails:
                log.warning(
                    "Email {} не подтверждён на странице-источнике; "
                    "контакт будет сохранён без него",
                    email,
                )
                if recipient_address and (
                    recipient_address.strip().lower()
                    == email.strip().lower()
                ):
                    recipient_address = None
                email = None
                if (preferred_channel or "").strip().lower() == "email":
                    preferred_channel = None

            if (preferred_channel or "").strip().lower() in {
                "contact_form",
                "form",
                "website_form",
            }:
                form_verification = next(
                    (
                        item
                        for item in verifications
                        if contact_form_url
                        and contact_form_url.rstrip("/")
                        in {
                            str(item.get("source_url") or "").rstrip("/"),
                            str(item.get("final_url") or "").rstrip("/"),
                        }
                    ),
                    None,
                )
                if form_verification is None and contact_form_url:
                    form_verification = await asyncio.to_thread(
                        verify_source,
                        contact_form_url,
                    )

                if not (
                    form_verification
                    and form_verification.get("verified")
                    and form_verification.get("has_contact_form")
                ):
                    page_emails = [
                        item.strip().lower()
                        for item in (
                            (form_verification or {}).get("emails") or []
                        )
                        if item.strip()
                    ]
                    replacement_email = (
                        email.strip().lower()
                        if email
                        and email.strip().lower() in verified_emails
                        else (page_emails[0] if page_emails else None)
                    )
                    if replacement_email:
                        log.info(
                            "URL {} не содержит интерактивной формы; "
                            "канал контакта {} переключён на email {}",
                            contact_form_url,
                            organization_name,
                            replacement_email,
                        )
                        email = replacement_email
                        preferred_channel = "email"
                        recipient_address = replacement_email
                        contact_form_url = None
                    else:
                        raise ValueError(
                            "Страница contact_form_url не содержит "
                            "интерактивной формы с полем сообщения и кнопкой "
                            "отправки; подтверждённый email также не найден"
                        )
        normalized_channel = (preferred_channel or "").strip().lower()
        if normalized_channel == "telegram" and not recipient_address:
            recipient_address = telegram_url or recipient_external_id
        generated_message = ensure_invitation(
            generated_message,
            organization_name=organization_name,
            category=category,
            preferred_channel=preferred_channel,
        )
        data = SaveContactToolArgs(
            search_run_id=search_run_id,
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
            contact_form_url=contact_form_url,
            vk_url=vk_url,
            telegram_url=telegram_url,
            ok_url=ok_url,
            youtube_url=youtube_url,
            rutube_url=rutube_url,
            dzen_url=dzen_url,
            source=source,
            relevance_score=relevance_score,
            relevance_reason=relevance_reason,
            preferred_channel=preferred_channel,
            generated_message=generated_message,
            recipient_address=recipient_address,
            recipient_external_id=recipient_external_id,
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

        contact_data["status"] = ContactStatus.PENDING_REVIEW.value
        contact_data["next_action"] = "Требуется проверка человеком"

        contact = await repository.create(contact_data)

        return {
            "success": True,
            "status": "created",
            "contact_id": contact.id,
            "message": "Организация сохранена",
        }
    except Exception as error:
        log.exception("Ошибка сохранения")
        return {
            "success": False,
            "status": "error",
            "message": str(error) or "Ошибка сохранения",
        }
