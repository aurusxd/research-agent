import asyncio
import os

from telethon import TelegramClient


async def main() -> None:
    client = TelegramClient(
        os.getenv(
            "TELEGRAM_USER_SESSION",
            "/app/telegram-session/outreach",
        ),
        int(os.environ["TELEGRAM_API_ID"]),
        os.environ["TELEGRAM_API_HASH"],
    )

    await client.start()
    me = await client.get_me()
    print(f"Авторизован аккаунт: {me.id}")
    await client.disconnect()


asyncio.run(main())