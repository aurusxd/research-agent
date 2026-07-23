from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart

from api.client import ApiClient
from services.logger import log
from telegram.command_handler import BotCommandHandler
from telegram.keyboards.callback import router as review_callback_router
from config import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
api_client = ApiClient()
dp = Dispatcher(api_client=api_client)
command_handler = BotCommandHandler(api_client=api_client)
dp.startup.register(command_handler.on_startup)
dp.shutdown.register(command_handler.on_shutdown)
dp.include_router(review_callback_router)

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await command_handler.start(message)

@dp.message(Command("review"))
async def review_handler(message: types.Message):
    await command_handler.review(message)

@dp.message()
async def message_handler(message: types.Message):
    """Перенаправляет входящие сообщения Telegram в обработчик команд."""
    user_id = str(message.from_user.id)
    username = message.from_user.username or message.from_user.first_name or "Unknown"
    text = message.text or ""
    log.info(f"Сообщение от {user_id}:{username}: {text}")

    await command_handler.handle_message(message)


