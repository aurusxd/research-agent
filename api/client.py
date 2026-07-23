from collections import OrderedDict
from typing import Any

import aiohttp

API_BASE_URL = "http://api:8000"
API_URL = f"{API_BASE_URL}/ask"
MAX_USER_SESSIONS = 50
SESSION_TIMEOUT_SECONDS = 200


class ResponseValidationError(Exception):
    pass


class EmptyResponseError(Exception):
    pass


class InvalidReviewResponseError(Exception):
    pass


class ApiClient:
    def __init__(self, max_sessions: int = MAX_USER_SESSIONS) -> None:
        """Инициализирует API-клиента с пулом сессий на пользователя."""
        self._max_sessions = max_sessions
        self._sessions: OrderedDict[str, aiohttp.ClientSession] = OrderedDict()

    async def _get_session(self, user_id: str) -> aiohttp.ClientSession:
        """Возвращает существующую сессию или создает новую для пользователя."""
        session = self._sessions.get(user_id)
        if session is not None and not session.closed:
            return session

        if session is not None and session.closed:
            self._sessions.pop(user_id, None)

        if len(self._sessions) >= self._max_sessions:
            _, oldest_session = self._sessions.popitem(last=False)
            if not oldest_session.closed:
                await oldest_session.close()

        timeout = aiohttp.ClientTimeout(total=SESSION_TIMEOUT_SECONDS)
        session = aiohttp.ClientSession(timeout=timeout)
        self._sessions[user_id] = session
        return session

    async def request(self, user_id: str, text: str) -> str:
        """Отправляет текст пользователя в backend API и возвращает проверенный ответ."""
        session = await self._get_session(user_id)
        async with session.post(API_URL, json={"user_id": user_id, "text": text}) as response:
            if response.status != 200:  # noqa: PLR2004
                body = await response.text()
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=body,
                    headers=response.headers,
                )
            data = await response.json()

        return self._validate_response(data)

    async def get_review_queue(self, user_id: str) -> list[dict[str, Any]]:
        """Возвращает контакты, ожидающие проверки оператором."""
        session = await self._get_session(user_id)
        url = f"{API_BASE_URL}/contacts/review"

        async with session.get(url) as response:
            if response.status != 200:  # noqa: PLR2004
                body = await response.text()
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=body,
                    headers=response.headers,
                )

            data = await response.json()

        if not isinstance(data, list) or not all(
            isinstance(contact, dict) for contact in data
        ):
            raise InvalidReviewResponseError

        return data

    async def review_contact(
        self,
        user_id: str,
        contact_id: int,
        action: str,
    ) -> dict[str, Any]:
        """Одобряет или отклоняет контакт через backend API."""
        if action not in {"approve", "reject"}:
            raise ValueError(f"Неизвестное действие проверки: {action}")

        session = await self._get_session(user_id)
        url = f"{API_BASE_URL}/contacts/{contact_id}/{action}"

        async with session.post(url) as response:
            if response.status != 200:  # noqa: PLR2004
                body = await response.text()
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=body,
                    headers=response.headers,
                )

            data = await response.json()

        if not isinstance(data, dict) or data.get("success") is not True:
            raise InvalidReviewResponseError

        return data

    def _validate_response(self, data: Any) -> str:
        """Валидирует содержимое ответа API и извлекает ответ."""
        if not isinstance(data, dict):
            raise ResponseValidationError

        answer = data.get("answer")
        if not isinstance(answer, str):
            raise ResponseValidationError

        answer = answer.strip()
        if answer == "":
            raise EmptyResponseError

        return answer

    async def close(self) -> None:
        """Закрывает все открытые пользовательские сессии и очищает пул сессий."""
        for session in list(self._sessions.values()):
            if not session.closed:
                await session.close()
        self._sessions.clear()
