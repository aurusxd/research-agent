import os
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright, expect

from services.delivery_errors import VkCaptchaRequired, VkSessionExpired


class OkService:
    @staticmethod
    async def send_message_playwright(
        url: str,
        message: str,
    ) -> dict[str, str | bool]:
        headless = os.getenv("OK_PLAYWRIGHT_HEADLESS", "true").lower() != "false"
        storage_state = os.getenv(
            "OK_PLAYWRIGHT_STORAGE_STATE",
            "ok_auth.json",
        )
        if not Path(storage_state).exists():
            raise VkSessionExpired(
                f"Не найден файл авторизации OK.ru: {storage_state}"
            )

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=headless)
            try:
                context = await browser.new_context(storage_state=storage_state)
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                body_text = (await page.locator("body").inner_text()).lower()
                if "captcha" in page.url.lower() or "капча" in body_text:
                    raise VkCaptchaRequired(
                        "OK.ru показал CAPTCHA и требует участия оператора"
                    )
                if "login" in page.url.lower() or "войти" in body_text[:1000]:
                    raise VkSessionExpired(
                        "Сессия OK.ru истекла, обновите ok_auth.json"
                    )

                await page.get_by_text("Написать", exact=True).click(
                    timeout=15_000
                )
                editor = page.locator(
                    'msg-message-editor[placeholder*="Напишите сообщение"], '
                    '[data-tsid="write_msg_portlet"] [contenteditable="true"], '
                    '[data-tsid="write_msg_portlet"] textarea'
                ).last
                await editor.wait_for(state="visible", timeout=15_000)
                await editor.fill(message)
                await page.get_by_role(
                    "button",
                    name="Отправить",
                ).click(timeout=15_000)
                try:
                    await expect(editor).to_be_empty(timeout=10_000)
                except (PlaywrightTimeoutError, AssertionError) as error:
                    raise RuntimeError(
                        "OK.ru не подтвердил отправку сообщения"
                    ) from error
                return {"success": True, "message_id": ""}
            finally:
                await browser.close()
