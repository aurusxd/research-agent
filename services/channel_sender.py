from typing import Any

from services.telegram_service import TelegramService

class ChannelConfigurationError(RuntimeError):
    pass


async def send_telegram_message(
    *,
    recipient_external_id: str,
    text: str,
) -> dict[str, Any]:
    return await TelegramService.send_message(
        recipient_external_id=recipient_external_id,
        text=text,
    )


async def send_vk_message(
    *,
    recipient_url: str,
    text: str,
) -> dict[str, Any]:
    if not recipient_url.startswith(("https://vk.com/", "http://vk.com/")):
        raise ChannelConfigurationError(
            "Для VK требуется проверенный URL профиля или сообщества"
        )
    from services.vk_service import VkService

    return await VkService.send_message_playwright(recipient_url, text)
