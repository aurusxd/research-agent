import os
from typing import Any

from dotenv import load_dotenv
import requests

from services.logger import log

load_dotenv()


class WebSearchError(RuntimeError):
    pass


def search_web_results(
    query: str,
    *,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    log.info("Поиск Tavily: {}", query)
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise WebSearchError("Не задан TAVILY_API_KEY")

    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()

        return [
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "content": item.get("content") or "",
                "score": item.get("score"),
                "query": query,
            }
            for item in data.get("results", [])
            if item.get("url")
        ]
    except requests.RequestException as error:
        log.exception("Ошибка Tavily API")
        raise WebSearchError(
            f"Не удалось выполнить запрос Tavily: {query}"
        ) from error
    except (TypeError, ValueError) as error:
        log.exception("Tavily вернул некорректный ответ")
        raise WebSearchError(
            "Tavily вернул некорректный ответ"
        ) from error


def search_web(query: str) -> str:
    results = search_web_results(query)
    return "\n---\n".join(
        (
            f"Название: {item['title']}\n"
            f"Ссылка: {item['url']}\n"
            f"Описание: {item['content']}\n"
        )
        for item in results
    )
