from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel

from agent.core import ask_agent
from database.repositories.contact_repository import ContactRepository
from schemas.contact import ContactRead
from utils.enums import ContactStatus
from database.session import AsyncSession, provider


app = FastAPI()

class RequestData(BaseModel):
    text: str

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