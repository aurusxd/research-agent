import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import Message
import aiohttp

from api.client import (
    ApiClient,
    EmptyResponseError,
    InvalidReviewResponseError,
    ResponseValidationError,
)
from services.logger import log
from telegram.keyboards.main import keyboard_build
from telegram.keyboards.menu import (
    MAILING_BUTTON,
    MAIN_MENU_BUTTONS,
    REVIEW_BUTTON,
    SEARCH_BUTTON,
    SETTINGS_BUTTON,
    STATISTICS_BUTTON,
    build_main_menu,
    build_mailing_menu,
    build_review_menu,
    build_search_menu,
    build_settings_menu,
    build_statistics_menu,
)
from telegram.review import build_review_card


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
        if text in MAIN_MENU_BUTTONS:
            await self.handle_main_menu(message, text)
            return
        if text.startswith("/"):
            await self.handle_command(message, text)
        else:
            await self.handle_api_request(message, text)

    async def handle_main_menu(self, message: Message, action: str) -> None:
        """Показывает выбранный экран меню без запуска бизнес-логики."""
        if action == SEARCH_BUTTON:
            await message.answer(
                "🔍 <b>Поиск</b>\n\nВыберите, кого должен искать агент.",
                reply_markup=build_search_menu(),
                parse_mode="HTML",
            )
        elif action == REVIEW_BUTTON:
            await message.answer(
                "📋 <b>Проверка материалов</b>\n\nВыберите очередь для ручной проверки.",
                reply_markup=build_review_menu(),
                parse_mode="HTML",
            )
        elif action == MAILING_BUTTON:
            await message.answer(
                "🚀 <b>Управление рассылкой</b>\n\n"
                "Статус: не запущена\n"
                "Отправлено сегодня: 0\n"
                "Осталось по лимиту: —",
                reply_markup=build_mailing_menu(),
                parse_mode="HTML",
            )
        elif action == STATISTICS_BUTTON:
            await message.answer(
                "📊 <b>Статистика</b>\n\n"
                "Найдено: —\n"
                "Ожидают проверки: —\n"
                "Одобрено: —\n"
                "Отправлено: —\n"
                "Ошибок: —",
                reply_markup=build_statistics_menu(),
                parse_mode="HTML",
            )
        elif action == SETTINGS_BUTTON:
            await message.answer(
                "⚙️ <b>Настройки агента</b>\n\n"
                "Интервал: не задан\n"
                "Дневной лимит: не задан\n"
                "Рабочее время: не задано\n"
                "Часовой пояс: Asia/Novosibirsk\n"
                "Автозапуск: выключен\n\n"
                "DeepSeek: ⚪ не проверено\n"
                "Tavily: ⚪ не проверено",
                reply_markup=build_settings_menu(),
                parse_mode="HTML",
            )

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
        await message.answer(
            "Бот «Корни» запущен. Выберите раздел меню или напишите задачу агенту.",
            reply_markup=build_main_menu(),
        )

    async def review(self, message: Message) -> None:
        """Показывает первый контакт из очереди проверки."""
        user_id = str(message.from_user.id)

        try:
            contacts = await self.api_client.get_review_queue(user_id)
        except aiohttp.ClientResponseError as exc:
            await message.answer(
                f"Ошибка API {exc.status}: не удалось получить очередь"
            )
            return
        except InvalidReviewResponseError:
            await message.answer("API вернул некорректную очередь контактов")
            return
        except Exception:  # noqa: BLE001
            log.exception("Ошибка получения контактов")
            await message.answer("Не удалось получить контакты на проверку")
            return

        if not contacts:
            await message.answer("Нет контактов на проверку")
            return

        contact = contacts[0]
        contact_id = contact.get("id")
        if not isinstance(contact_id, int):
            await message.answer("API вернул контакт без корректного ID")
            return

        await message.answer(
            build_review_card(contact),
            reply_markup=keyboard_build(contact_id),
        )

    async def on_startup(self, dispatcher: Dispatcher, bot: Bot):  # noqa: ARG002
        me = await bot.get_me()
        log.success(f"Бот {me.username} успешно запущен!")

    async def on_shutdown(self, dispatcher: Dispatcher, bot: Bot):  # noqa: ARG002
        await self.api_client.close()

