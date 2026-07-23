import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import Message
import aiohttp

from api.client import ApiClient, EmptyResponseError, ResponseValidationError
from services.logger import log


class BotCommandHandler:
    def __init__(self, api_client: ApiClient):
        """Инициализирует обработчик команд с API и сервисом напоминаний."""
        self.api_client = api_client

    async def _send_message(self, message: Message, text: str) -> None:
        """Отправляет сообщение и логирует его."""
        user_id = str(message.from_user.id)
        username = message.from_user.username or message.from_user.first_name or "Unknown"
        await message.answer(text)
        log.info(f"Сообщение от {user_id}:{username}: ",text)

    async def handle_message(self, message: Message) -> None:
        """Направляет входящее сообщение на обработку команды или запрос в ИИ."""
        text = (message.text or "").strip()
        if text.startswith("/"):
            await self.handle_command(message, text)
        else:
            await self.handle_api_request(message, text)
    async def handle_api_request(self,message: Message,text: str) -> None:
        """Отправляет текст без команды в backend ИИ и возвращает ответ."""
        user_id = str(message.from_user.id)
        try:
            answer = await self.api_client.request(user_id=user_id, text=text)
        except aiohttp.ClientResponseError as exc:
            await message.answer(f"API error {exc.status}: {exc.message}")
            return
        except asyncio.TimeoutError:
            await message.answer("Request timed out after 200 seconds.")
            return
        except EmptyResponseError:
            await message.answer("пустой ответ")
            return
        except ResponseValidationError:
            await message.answer("ошибка в ответе")
            return
        except Exception as exc:  # noqa: BLE001
            await message.answer(f"Unexpected error: {exc}")
            return

        await message.answer(answer)

    async def start(self, message: Message) -> None:
        """Отвечает на /start простым подтверждением запуска."""
        log.info("Вызвана команда /start")
        await message.answer("Бот запущен")


    async def on_startup(self, dispatcher: Dispatcher, bot: Bot):  # noqa: ARG002
        me = await bot.get_me()
        log.success(f"Бот {me.username} успешно запущен!")

