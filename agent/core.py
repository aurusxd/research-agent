import json
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI
from pydantic import ValidationError

from agent.tools.web_search import search_web
from agent.tools.save_contact import save_contact
from schemas.save_contact_schema import SaveContactToolArgs
import inspect

from schemas.search_run import SearchPlan
from utils.prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_FOR_QUERY
load_dotenv()

client = AsyncOpenAI(
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

async def create_search_plan(
        user_query: str,
    ) -> dict:
        user_query = user_query.strip()

        if not user_query:
            raise ValueError("Пользовательский запрос не может быть пустым")

        response = await client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT_FOR_QUERY,
                },
                {
                    "role": "user",
                    "content": (
                        "Разбери следующий запрос и верни JSON:\n"
                        f"{user_query}"
                    ),
                },
            ],
            response_format={
                "type": "json_object",
            },
            temperature=0.2,
            max_tokens=1000,
        )

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(
                "DeepSeek вернул пустой ответ"
            )

        try:
            raw_data = json.loads(content)
            plan = SearchPlan.model_validate(raw_data)

        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"DeepSeek вернул некорректный JSON: {content}"
            ) from error

        except ValidationError as error:
            raise RuntimeError(
                f"Ответ DeepSeek не соответствует схеме: {error}"
            ) from error

        # Убираем возможные дубли, сохраняя порядок.
        unique_queries = list(dict.fromkeys(plan.queries))

        if len(unique_queries) < 3:
            raise RuntimeError(
                "DeepSeek сформировал меньше трёх уникальных запросов"
            )

        plan.queries = unique_queries

        return plan.model_dump()


async def ask_agent(
    user_message: str,
    search_run_id: int | None = None,
) -> str:
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,  # noqa: RUF001
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]
    if search_run_id is not None:
        messages.insert(
            1,
            {
                "role": "system",
                "content": (
                    f"Текущий search_run_id={search_run_id}. "
                    "Обязательно передавай его в каждый вызов save_contact."
                ),
            },
        )

    for _ in range(MAX_TOOL_ROUNDS):
        response = await client.chat.completions.create(
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

