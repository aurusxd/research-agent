import asyncio

from services.logger import log
from telegram.bot import bot, dp
from telegram.keyboards.callback import router as callback_router


async def main():


    dp.include_router(callback_router)
    try:
        log.info("🚀 Запуск бота")
        await dp.start_polling(bot, timeout=60)
    except Exception:  # noqa: BLE001
        log.exception("Бот не запущен, ошибка: ")





if __name__ == "__main__":
    asyncio.run(main())

