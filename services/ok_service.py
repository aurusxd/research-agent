import os
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Page, async_playwright

from services.delivery_errors import VkCaptchaRequired, VkSessionExpired


CAPTCHA_TEXT = re.compile(
    r"captcha|капч|код с картинки|не робот",
    re.IGNORECASE,
)
LOGIN_TEXT = re.compile(
    r"войти|вход|номер телефона|почта или телефон",
    re.IGNORECASE,
)
WRITE_TEXT = re.compile(
    r"^(написать|написать сообщение|сообщение)$",
    re.IGNORECASE,
)
SEND_TEXT = re.compile(r"^отправить", re.IGNORECASE)


async def locator_is_visible(locator) -> bool:
    try:
        return await locator.first.is_visible()
    except Exception:
        return False


async def detect_blocking_state(page: Page) -> str | None:
    body_text = await page.locator("body").inner_text(timeout=10_000)
    captcha_locator = page.locator(
        'iframe[src*="captcha" i], '
        '[class*="captcha" i], '
        '[id*="captcha" i], '
        'input[name*="captcha" i]'
    )
    if (
        "captcha" in page.url.lower()
        or CAPTCHA_TEXT.search(body_text)
        or await locator_is_visible(captcha_locator)
    ):
        return "captcha"

    password = page.locator('input[type="password"]')
    login_form = page.locator(
        'form[action*="login" i], input[name="email"], input[name="phone"]'
    )
    if (
        "login" in page.url.lower()
        or await locator_is_visible(password)
        or await locator_is_visible(login_form)
        or LOGIN_TEXT.search(body_text[:1500])
    ):
        return "session_expired"
    return None


async def find_write_control(page: Page):
    button = page.get_by_role("button", name=WRITE_TEXT)
    if await locator_is_visible(button):
        return button.first

    link = page.get_by_role("link", name=WRITE_TEXT)
    if await locator_is_visible(link):
        return link.first

    text = page.get_by_text(WRITE_TEXT)
    if await locator_is_visible(text):
        return text.first
    return None


def _screenshot_path(directory: Path, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"ok-{label}-{stamp}.png"


async def _raise_if_blocked(page: Page, screenshot_dir: Path) -> None:
    state = await detect_blocking_state(page)
    if state == "captcha":
        screenshot = _screenshot_path(screenshot_dir, "captcha")
        await page.screenshot(path=str(screenshot), full_page=True)
        raise VkCaptchaRequired(str(screenshot))
    if state == "session_expired":
        raise VkSessionExpired(
            "Сессия OK.ru истекла, обновите ok_auth.json"
        )


async def prepare_profile_page(
    page: Page,
    url: str,
    *,
    screenshot_dir: Path = Path("/tmp"),
):
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(2_000)
    await _raise_if_blocked(page, screenshot_dir)

    write_control = await find_write_control(page)
    if write_control is None:
        screenshot = _screenshot_path(screenshot_dir, "write-control-missing")
        await page.screenshot(path=str(screenshot), full_page=True)
        raise RuntimeError(
            "OK.ru не предоставил кнопку «Написать»; возможно, сообщения "
            "закрыты или изменилась разметка. "
            f"Screenshot: {screenshot}"
        )
    return write_control


async def send_message_on_page(
    page: Page,
    url: str,
    message: str,
    *,
    screenshot_dir: Path = Path("/tmp"),
) -> dict[str, str | bool]:
    write_control = await prepare_profile_page(
        page,
        url,
        screenshot_dir=screenshot_dir,
    )
    await write_control.click(timeout=15_000)
    await _raise_if_blocked(page, screenshot_dir)

    editor = page.locator(
        'msg-message-editor[placeholder*="Напишите сообщение"], '
        '[data-tsid="write_msg_portlet"] [contenteditable="true"], '
        '[data-tsid="write_msg_portlet"] textarea'
    ).last
    await editor.wait_for(state="visible", timeout=15_000)
    await editor.fill(message)

    send_button = page.get_by_role("button", name=SEND_TEXT)
    if not await locator_is_visible(send_button):
        screenshot = _screenshot_path(screenshot_dir, "send-control-missing")
        await page.screenshot(path=str(screenshot), full_page=True)
        raise RuntimeError(
            "OK.ru не предоставил кнопку «Отправить». "
            f"Screenshot: {screenshot}"
        )
    await send_button.first.click(timeout=15_000)

    try:
        await editor.wait_for(state="visible", timeout=3_000)
        tag_name = await editor.evaluate(
            "(element) => element.tagName.toLowerCase()"
        )
        remaining = (
            await editor.input_value()
            if tag_name in {"input", "textarea"}
            else await editor.inner_text()
        ).strip()
    except Exception:
        # OK.ru may replace the editor after a successful send.
        remaining = ""

    if remaining:
        screenshot = _screenshot_path(screenshot_dir, "send-not-confirmed")
        await page.screenshot(path=str(screenshot), full_page=True)
        raise RuntimeError(
            "OK.ru не подтвердил отправку: редактор сообщения не очистился. "
            f"Screenshot: {screenshot}"
        )
    return {"success": True, "message_id": ""}


class OkService:
    @staticmethod
    async def send_message_playwright(
        url: str,
        message: str,
    ) -> dict[str, str | bool]:
        headless = (
            os.getenv("OK_PLAYWRIGHT_HEADLESS", "true").lower() != "false"
        )
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
                return await send_message_on_page(page, url, message)
            finally:
                await browser.close()
