import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from agent.tools.web_search import search_web
from agent.tools.save_contact import save_contact
from schemas.save_contact_schema import SaveContactToolArgs
import inspect
load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

MAX_TOOL_ROUNDS = 20

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Ищет актуальную информацию в интернете",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос",
                    }
                },
                "required": ["query"],
            },
        },
        
    },

    {
        "type": "function",
        "function": {
            "name": "save_contact",
            "description": (
                "Сохраняет найденную организацию и её публичные "
                "контактные данные в базу данных. Вызывай после того, "
                "как информация проверена через web_search."
            ),
            "parameters": SaveContactToolArgs.model_json_schema(),
        },
    },
]


available_tools = {
    "search_web": search_web,
    "save_contact": save_contact,
}


async def ask_agent(user_message: str) -> str:
    messages = [
        {
            "role": "system",
            "content": """
Ты — AI-агент по поиску потенциальных клиентов.

У тебя есть два инструмента:

1. web_search — поиск информации в интернете.
2. save_contact — сохранение найденной организации в базу данных.

Алгоритм работы:

1. Получи критерии поиска от пользователя.
2. Используй web_search для поиска подходящих организаций.
3. Для каждой организации найди:
   - официальное название;
   - официальный сайт;
   - город и регион;
   - сферу деятельности;
   - публичный email;
   - публичный телефон;
   - официальные страницы в социальных сетях;
   - имя и должность контактного лица, если они опубликованы.
4. Проверь, что найденные страницы действительно относятся к организации.
5. Оцени релевантность организации от 0 до 100.
6. Объясни причину оценки.
7. Для каждой подходящей организации отдельно вызови save_contact.

Правила:

- Не придумывай отсутствующие данные.
- Для неизвестных необязательных полей передавай null.
- Не сохраняй организацию без названия и источника.
- Не сохраняй организацию, если она не соответствует критериям.
- Не утверждай, что организация сохранена, пока save_contact
  не вернул успешный результат.
- Не вызывай save_contact повторно для одной и той же организации.
""",  # noqa: RUF001
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            extra_body={"thinking": {"type": "disabled"}},
        )

        message = response.choices[0].message
        messages.append(message)

        if not message.tool_calls:
            return message.content or "Задача завершена."

        # Обязательно ответить на КАЖДЫЙ tool_call
        for tool_call in message.tool_calls:
            try:
                function_name = tool_call.function.name
                function = available_tools.get(function_name)

                if function is None:
                    raise ValueError(
                        f"Неизвестный инструмент: {function_name}"
                    )

                arguments = json.loads(
                    tool_call.function.arguments
                )

                tool_result = function(**arguments)

                if inspect.isawaitable(tool_result):
                    tool_result = await tool_result

                content = json.dumps(
                    {
                        "success": True,
                        "result": tool_result,
                    },
                    ensure_ascii=False,
                    default=str,
                )

            except Exception as error:
                # Даже при ошибке инструмента необходимо добавить
                # сообщение с соответствующим tool_call_id.
                content = json.dumps(
                    {
                        "success": False,
                        "error": str(error),
                    },
                    ensure_ascii=False,
                )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": content,
                }
            )

    return (
        "Не удалось завершить задачу: "
        "превышено число вызовов инструментов."
    )

