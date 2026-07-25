import os

from fastapi import FastAPI, Depends, HTTPException
from fastapi import Request
from pydantic import BaseModel

from database.repositories.contact_repository import ContactRepository
from schemas.contact import ContactRead
from schemas.search_run import SearchRunCreate, SearchRunRead
from schemas.statistics import StatisticsRead
from services.search_run_service import SearchRunService
from services.statistics_service import StatisticsPeriod, StatisticsService
from services.mailing_queue_service import mailing_queue
from utils.enums import ContactStatus
from database.session import AsyncSession, provider


app = FastAPI()


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    expected = os.getenv("INTERNAL_API_KEY", "").strip()
    if (
        expected
        and request.url.path != "/health"
        and request.headers.get("X-API-Key") != expected
    ):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)

class RequestData(BaseModel):
    text: str


class UpdateMessageRequest(BaseModel):
    message: str


class ContactResponseRequest(BaseModel):
    response: str
    interested: bool = False


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
async def ask(
    data: RequestData,
    session: AsyncSession = Depends(provider.get_session),
):
    """Запускает управляемый поиск из обычного сообщения оператора."""
    service = SearchRunService(session)
    search_run = await service.create_and_execute(
        SearchRunCreate(query=data.text)
    )

    return {
        "answer": (
            search_run.agent_result
            or search_run.error_message
            or "Поиск завершён без текстового результата."
        ),
        "search_run_id": search_run.id,
        "status": search_run.status,
        "search_queries": search_run.search_queries,
        "found_count": search_run.found_count,
        "saved_count": search_run.saved_count,
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


@app.get("/contacts", response_model=list[ContactRead])
async def list_contacts(
    status: ContactStatus | None = None,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(provider.get_session),
):
    repository = ContactRepository(session)
    contacts = await repository.search(
        status=status.value if status else None,
        limit=max(1, min(limit, 100)),
        offset=max(0, offset),
    )
    return [
        ContactRead.model_validate(contact)
        for contact in contacts
    ]


@app.get("/statistics", response_model=StatisticsRead)
async def get_statistics(
    period: StatisticsPeriod = "all",
    session: AsyncSession = Depends(provider.get_session),
):
    return await StatisticsService(session).get(period)


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

    try:
        queue = await mailing_queue.enqueue_contact(
            contact.id,
            contact.preferred_channel,
        )
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "Контакт одобрен, но Redis/Celery недоступен. "
                "Запустите рассылку повторно."
            ),
        ) from error
    await session.refresh(contact)

    return {
        "success": True,
        "contact_id": contact.id,
        "status": contact.status,
        "queue": queue,
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


@app.patch("/contacts/{contact_id}/message")
async def update_contact_message(
    contact_id: int,
    data: UpdateMessageRequest,
    session: AsyncSession = Depends(provider.get_session),
):
    contact = await ContactRepository(session).get_by_id(contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Контакт не найден")
    if contact.status != ContactStatus.PENDING_REVIEW.value:
        raise HTTPException(
            status_code=409,
            detail="Редактировать можно только до одобрения",
        )
    message = data.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Текст не может быть пустым")
    contact.generated_message = message
    await session.commit()
    return {
        "success": True,
        "contact_id": contact_id,
        "status": contact.status,
    }


@app.post("/contacts/{contact_id}/response")
async def register_contact_response(
    contact_id: int,
    data: ContactResponseRequest,
    session: AsyncSession = Depends(provider.get_session),
):
    contact = await ContactRepository(session).get_by_id(contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Контакт не найден")
    contact.response = data.response.strip()
    contact.status = (
        ContactStatus.INTERESTED.value
        if data.interested
        else ContactStatus.REPLIED.value
    )
    contact.next_action = (
        "Передать заинтересованного участника ответственному"
        if data.interested
        else "Оценить ответ и определить следующее действие"
    )
    await session.commit()
    return {"success": True, "contact_id": contact_id, "status": contact.status}


@app.get("/mailing/status")
async def get_mailing_status():
    return await mailing_queue.status()


@app.post("/mailing/{action}")
async def control_mailing(action: str):
    actions = {
        "start": mailing_queue.start,
        "pause": mailing_queue.pause,
        "resume": mailing_queue.resume,
        "stop": mailing_queue.stop,
    }
    handler = actions.get(action)
    if handler is None:
        raise HTTPException(
            status_code=400,
            detail="Допустимые действия: start, pause, resume, stop",
        )
    return await handler()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
