from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import ask_agent
from database.models import SearchRun
from database.repositories.search_run_repository import SearchRunRepository
from schemas.search_run import SearchRunCreate
from utils.enums import SearchRunStatus


class SearchRunService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = SearchRunRepository(session)

    async def create_and_execute(self, data: SearchRunCreate) -> SearchRun:
        search_run = await self.repository.create(
            data.model_dump(mode="json")
        )
        await self.session.commit()

        search_run.status = SearchRunStatus.RUNNING.value
        search_run.started_at = datetime.now(timezone.utc)
        await self.session.commit()

        try:
            agent_result = await ask_agent(
                user_message=self._build_agent_task(search_run),
                search_run_id=search_run.id,
            )
            search_run.saved_count = await self.repository.count_contacts(
                search_run.id
            )
            search_run.found_count = search_run.saved_count
            search_run.agent_result = agent_result
            search_run.status = SearchRunStatus.COMPLETED.value
        except Exception as error:
            search_run.status = SearchRunStatus.FAILED.value
            search_run.error_count += 1
            search_run.error_message = str(error)[:4000]

        search_run.finished_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(search_run)
        return search_run

    async def get_by_id(self, search_run_id: int) -> SearchRun | None:
        return await self.repository.get_by_id(search_run_id)

    async def get_all(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SearchRun]:
        return await self.repository.get_all(limit=limit, offset=offset)

    @staticmethod
    def _build_agent_task(search_run: SearchRun) -> str:
        parts = [
            search_run.query,
            f"ID поискового запуска: {search_run.id}.",
            "Передавай этот ID в search_run_id при каждом вызове save_contact.",
            f"Сохрани не более {search_run.requested_limit} уникальных контактов.",
            (
                "Сохраняй только контакты с релевантностью не ниже "
                f"{search_run.min_relevance_score}."
            ),
        ]
        if search_run.category:
            parts.append(f"Категория: {search_run.category}.")
        if search_run.country:
            parts.append(f"Страна: {search_run.country}.")
        if search_run.region:
            parts.append(f"Регион: {search_run.region}.")
        if search_run.city:
            parts.append(f"Город: {search_run.city}.")
        if search_run.keywords:
            parts.append(
                f"Дополнительные ключевые слова: {', '.join(search_run.keywords)}."
            )
        if search_run.excluded_keywords:
            parts.append(
                "Исключи результаты со словами: "
                f"{', '.join(search_run.excluded_keywords)}."
            )
        parts.append(
            "Для каждого результата сначала проверь данные через web_search, "
            "затем сохрани его через save_contact."
        )
        return "\n".join(parts)
