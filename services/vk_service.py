import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright, expect

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
                await page.goto(url, wait_until="commit", timeout=30000)
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

                page.locator('button:has-text("Подписаться")').click()
                await asyncio.sleep(2)
                open_dialog = page.locator(
                    'a[href^="/write"], '
                    'a[href*="/write"], '
                    'a:has-text("Сообщение"), '
                    'button:has-text("Сообщение"), '
                    'a:has-text("Написать сообщение"), '
                    'button:has-text("Написать сообщение")'
                ).first
                try:
                    if await open_dialog.is_visible():
                        await open_dialog.click(timeout=10_000)
                    else:
                        await page.get_by_text("Сообщение", exact=True).click()
                except (PlaywrightTimeoutError, AssertionError) as error:
                    raise RuntimeError(
                        "VK не предоставил кнопку отправки сообщения; "
                        "возможно, сообщения закрыты или изменилась разметка"
                    ) from error

                editor = page.locator(
                    '[contenteditable="true"][role="textbox"], '
                    '[contenteditable="true"], '
                    'textarea'
                ).last
                await editor.wait_for(state="visible", timeout=15_000)
                await editor.fill(message)
                await asyncio.sleep(1)
                send_button = page.locator(
                    '[aria-label="Отправить сообщение"], '
                    'button:has-text("Отправить")'
                ).first
                await page.keyboard.press("Enter")

                try:
                    await expect(editor).to_be_empty(timeout=10_000)
                except PlaywrightTimeoutError as error:
                    raise RuntimeError(
                        "VK не подтвердил отправку: редактор сообщения "
                        "не очистился после команды отправки"
                    ) from error
                return {"success": True, "message_id": ""}
            finally:
                await browser.close()

    
        
