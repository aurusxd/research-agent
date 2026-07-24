from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel

from agent.core import ask_agent
from database.repositories.contact_repository import ContactRepository
from schemas.contact import ContactRead
from schemas.search_run import SearchRunCreate, SearchRunRead
from services.search_run_service import SearchRunService
from services.mailing_service import (
    ContactAlreadySentError,
    ContactMailingError,
    ContactMailingService,
    ContactNotReadyError,
)
from utils.enums import ContactStatus
from database.session import AsyncSession, provider


app = FastAPI()

class RequestData(BaseModel):
    text: str


class SendEmailRequest(BaseModel):
    subject: str | None = None


@app.post("/search-runs", response_model=SearchRunRead)
async def create_search_run(
    data: SearchRunCreate,
    session: AsyncSession = Depends(provider.get_session),
):
    service = SearchRunService(session)
    return await service.create_and_execute(data)


@app.get("/search-runs", response_model=list[SearchRunRead])
async def list_search_runs(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(provider.get_session),
):
    service = SearchRunService(session)
    return await service.get_all(
        limit=max(1, min(limit, 100)),
        offset=max(0, offset),
    )


@app.get("/search-runs/{search_run_id}", response_model=SearchRunRead)
async def get_search_run(
    search_run_id: int,
    session: AsyncSession = Depends(provider.get_session),
):
    service = SearchRunService(session)
    search_run = await service.get_by_id(search_run_id)
    if search_run is None:
        raise HTTPException(status_code=404, detail="Поисковый запуск не найден")
    return search_run

@app.post("/ask")
async def ask(data: RequestData):
    """Обрабатывает ввод пользователя через ИИ-агента и возвращает результат."""
    result = await ask_agent(
        user_message=data.text,
    )

    return {
        "answer": result
    }


@app.get("/contacts/review")
async def get_review_queue(
    session: AsyncSession = Depends(provider.get_session),
):
    repository = ContactRepository(session)

    contacts = await repository.search(
        status=ContactStatus.PENDING_REVIEW.value,
        limit=20,
    )

    return [
        ContactRead.model_validate(contact)
        for contact in contacts
    ]


@app.post("/contacts/{contact_id}/approve")
async def approve_contact(
    contact_id: int,
    session: AsyncSession = Depends(provider.get_session),
):
    repository = ContactRepository(session)
    contact = await repository.get_by_id(contact_id)

    if contact is None:
        raise HTTPException(
            status_code=404,
            detail="Контакт не найден",
        )

    if contact.status != ContactStatus.PENDING_REVIEW.value:
        raise HTTPException(
            status_code=409,
            detail="Контакт уже был обработан",
        )

    contact.status = ContactStatus.APPROVED.value
    contact.next_action = "Готов к отправке"

    await session.commit()

    return {
        "success": True,
        "contact_id": contact.id,
        "status": contact.status,
    }


@app.post("/contacts/{contact_id}/reject")
async def reject_contact(
    contact_id: int,
    session: AsyncSession = Depends(provider.get_session),
):
    repository = ContactRepository(session)
    contact = await repository.get_by_id(contact_id)

    if contact is None:
        raise HTTPException(
            status_code=404,
            detail="Контакт не найден",
        )

    if contact.status != ContactStatus.PENDING_REVIEW.value:
        raise HTTPException(
            status_code=409,
            detail="Контакт уже был обработан",
        )

    contact.status = ContactStatus.REJECTED.value
    contact.next_action = None

    await session.commit()

    return {
        "success": True,
        "contact_id": contact.id,
        "status": contact.status,
    }


@app.post("/contacts/{contact_id}/send-email")
async def send_contact_email(
    contact_id: int,
    data: SendEmailRequest | None = None,
    session: AsyncSession = Depends(provider.get_session),
):
    service = ContactMailingService(session)
    try:
        communication, message_id = await service.send_approved_email(
            contact_id,
            subject=data.subject if data else None,
        )
    except ContactAlreadySentError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ContactNotReadyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ContactMailingError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return {
        "success": True,
        "contact_id": contact_id,
        "communication_id": communication.id,
        "status": ContactStatus.SENT.value,
        "message_id": message_id,
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
