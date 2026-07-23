import os

from dotenv import load_dotenv
import requests

from services.logger import log

load_dotenv()


def search_web(query: str) -> str:
    log.info("Зашел в search_web")
    api_key = os.getenv("TAVILY_API_KEY")

    try:
        response = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 5,
                },
                timeout=15,
            )
        
        response.raise_for_status()
        data = response.json()
        
        results = []
        
        for item in data.get("results", []):
            title = item.get("title")
            url = item.get("url")
            content = item.get("content")
        
            results.append(
                    f"Название: {title}\n"
                    f"Ссылка: {url}\n"
                    f"Описание: {content}\n"
                )
        
        return "\n---\n".join(results)
    except Exception:
        log.exception("Ошибка входа в tavily api: ")
