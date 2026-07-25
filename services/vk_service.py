import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright
from services.delivery_errors import VkCaptchaRequired, VkSessionExpired


class VkService:
    @staticmethod
    async def send_message_playwright(
        url: str,
        message: str,
    ) -> dict[str, str | bool]:
        """Функция отправки сообщения через автоматизацию браузера"""
        async with async_playwright() as p:
            headless = os.getenv("VK_PLAYWRIGHT_HEADLESS", "true").lower() != "false"
            storage_state = os.getenv(
                "VK_PLAYWRIGHT_STORAGE_STATE",
                "vk_auth.json",
            )
            browser = await p.chromium.launch(headless=headless)
            try:
                context = await browser.new_context(
                    storage_state=storage_state
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                page_text = (await page.locator("body").inner_text()).lower()
                if "captcha" in page.url.lower() or "введите код с картинки" in page_text:
                    screenshot = str(
                        Path("/tmp")
                        / f"vk-captcha-{datetime.now(timezone.utc).timestamp():.0f}.png"
                    )
                    await page.screenshot(path=screenshot, full_page=True)
                    raise VkCaptchaRequired(screenshot)
                if "login" in page.url.lower() or "войти" in page_text[:1000]:
                    raise VkSessionExpired(
                        "VK-сессия истекла, обновите vk_auth.json"
                    )
                await page.get_by_text("Сообщение", exact=True).click()
                await page.locator('[aria-label="Сообщение"]').fill(message)
                await asyncio.sleep(1)
                await page.locator(
                    '[aria-label="Отправить сообщение"]'
                ).click()
                await page.wait_for_timeout(1000)
                return {"success": True, "message_id": ""}
            finally:
                await browser.close()

    
        
