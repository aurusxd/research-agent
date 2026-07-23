from fastapi import FastAPI
from pydantic import BaseModel

from agent.core import ask_agent

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
