import asyncio
import os

from playwright.async_api import async_playwright


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

    
        
