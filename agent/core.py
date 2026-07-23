import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from agent.tools.web_search import search_web
from agent.tools.save_contact import save_contact
from schemas.save_contact_schema import SaveContactToolArgs
import inspect

from utils.prompt import SYSTEM_PROMPT
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
            "content": SYSTEM_PROMPT,  # noqa: RUF001
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

