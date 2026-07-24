import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import ask_agent, create_search_plan
from agent.tools.web_search import search_web_results
from database.models import SearchRun
from database.repositories.search_run_repository import SearchRunRepository
from services.logger import log
from schemas.search_run import SearchRunCreate
from services.search_query_planner import (
    build_search_queries,
    merge_search_results,
)
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
        try:
            plan = await create_search_plan(search_run.query)

            search_run.category = search_run.category or plan["category"]
            search_run.region = search_run.region or plan["region"]
            search_run.search_queries = plan["queries"][
                :search_run.search_queries_limit
    ]
        except Exception as error:
            log.warning(
            "ИИ-планировщик недоступен, используем резервный: {}",
            error,
            )
            search_run.search_queries = build_search_queries(search_run)
        await self.session.commit()

        try:
            search_results, errors = await self._execute_search_queries(
                search_run.search_queries
            )
            unique_results = merge_search_results(search_results)
            analysis_limit = min(
                50,
                max(20, search_run.requested_limit * 2),
            )
            analysis_results = sorted(
                unique_results,
                key=lambda item: float(item.get("score") or 0),
                reverse=True,
            )[:analysis_limit]

            search_run.executed_query_count = (
                len(search_run.search_queries) - len(errors)
            )
            search_run.raw_result_count = len(search_results)
            search_run.found_count = len(unique_results)
            search_run.duplicate_count = max(
                0,
                len(search_results) - len(unique_results),
            )
            search_run.error_count = len(errors)
            search_run.error_message = (
                "\n".join(errors)[:4000] if errors else None
            )
            await self.session.commit()

            if not unique_results:
                raise RuntimeError(
                    "Поисковые запросы не вернули ни одного результата"
                )

            agent_result = await ask_agent(
                user_message=self._build_agent_task(
                    search_run,
                    analysis_results,
                ),
                search_run_id=search_run.id,
            )
            search_run.saved_count = await self.repository.count_contacts(
                search_run.id
            )
            search_run.agent_result = agent_result
            search_run.status = (
                SearchRunStatus.PARTIALLY_COMPLETED.value
                if errors
                else SearchRunStatus.COMPLETED.value
            )
        except Exception as error:
            search_run.status = SearchRunStatus.FAILED.value
            search_run.error_count = max(1, search_run.error_count)
            previous_error = search_run.error_message or ""
            search_run.error_message = (
                f"{previous_error}\n{error}".strip()[:4000]
            )

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
    async def _execute_search_queries(
        queries: list[str],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        semaphore = asyncio.Semaphore(3)

        async def execute(query: str) -> list[dict[str, Any]]:
            async with semaphore:
                return await asyncio.to_thread(
                    search_web_results,
                    query,
                    max_results=10,
                )

        tasks = [
            execute(query)
            for query in queries
        ]
        responses = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )
        results: list[dict[str, Any]] = []
        errors: list[str] = []
        for query, response in zip(queries, responses, strict=True):
            if isinstance(response, BaseException):
                errors.append(f"{query}: {response}")
                continue
            results.extend(response)
        return results, errors

    @staticmethod
    def _build_agent_task(
        search_run: SearchRun,
        search_results: list[dict[str, Any]],
    ) -> str:
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
            "Ниже приведена уже собранная и очищенная от повторяющихся URL "
            "поисковая выдача. Проанализируй каждый результат. При "
            "необходимости используй web_search для проверки контактов, "
            "после чего сохраняй подходящие организации через save_contact."
        )
        for number, result in enumerate(search_results, start=1):
            content = " ".join(
                str(result.get("content") or "").split()
            )[:1200]
            parts.append(
                "\n".join(
                    [
                        f"Результат {number}:",
                        f"Название: {result.get('title') or 'Не указано'}",
                        f"URL: {result.get('url')}",
                        f"Описание: {content}",
                        (
                            "Найден по запросам: "
                            + ", ".join(
                                result.get("matched_queries") or []
                            )
                        ),
                    ]
                )
            )
        return "\n".join(parts)
