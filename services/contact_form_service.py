import os
import re

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

class ContactFormSendError(RuntimeError):
    pass


class ContactFormService:
    @staticmethod
    async def submit(
        *,
        url: str,
        message: str,
        organization_name: str,
    ) -> dict[str, str | bool]:
        headless = (
            os.getenv("CONTACT_FORM_PLAYWRIGHT_HEADLESS", "true").lower()
            != "false"
        )
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=headless)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                body_text = (await page.locator("body").inner_text()).lower()
                if any(
                    marker in body_text
                    for marker in ("captcha", "капча", "я не робот", "recaptcha")
                ):
                    raise ContactFormSendError(
                        "Форма содержит CAPTCHA и требует участия оператора"
                    )

                await ContactFormService._fill_optional(
                    page,
                    'input[type="email"], input[name*="email" i]',
                    os.getenv("MAILRU_SMTP_USER", ""),
                )
                await ContactFormService._fill_optional(
                    page,
                    'input[name*="name" i], input[autocomplete="name"]',
                    os.getenv(
                        "CONTACT_FORM_SENDER_NAME",
                        "Проект «Корни»",
                    ),
                )
                await ContactFormService._fill_optional(
                    page,
                    'input[name*="subject" i], input[name*="theme" i]',
                    f"Приглашение для {organization_name}",
                )

                editor = page.locator(
                    'textarea, [contenteditable="true"][role="textbox"], '
                    '[contenteditable="true"]'
                ).first
                await editor.wait_for(state="visible", timeout=15_000)
                await editor.fill(message)

                consent = page.locator(
                    'input[type="checkbox"][required], '
                    'input[type="checkbox"][name*="consent" i], '
                    'input[type="checkbox"][name*="agree" i]'
                )
                for index in range(await consent.count()):
                    checkbox = consent.nth(index)
                    if not await checkbox.is_checked():
                        await checkbox.check()

                submit = page.locator(
                    'button[type="submit"], input[type="submit"], '
                    'button:has-text("Отправить"), '
                    'button:has-text("Submit")'
                ).first
                await submit.click(timeout=15_000)
                try:
                    await page.wait_for_function(
                        """() => /спасибо|отправлен|успешно|thank you|success/i
                        .test(document.body.innerText)""",
                        timeout=15_000,
                    )
                except PlaywrightTimeoutError as error:
                    raise ContactFormSendError(
                        "Сайт не подтвердил успешную отправку формы"
                    ) from error
                return {"success": True, "message_id": page.url}
            finally:
                await browser.close()

    @staticmethod
    async def _fill_optional(page, selector: str, value: str) -> None:
        if not value:
            return
        locator = page.locator(selector).first
        if await locator.count() and await locator.is_visible():
            await locator.fill(value)
