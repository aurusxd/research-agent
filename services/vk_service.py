import os
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Page, async_playwright

from services.delivery_errors import VkCaptchaRequired, VkSessionExpired


CAPTCHA_TEXT = re.compile(
    r"captcha|капч|код с картинки|не робот|провер(ка|ьте).*(безопасност|человек)",
    re.IGNORECASE,
)
LOGIN_TEXT = re.compile(
    r"войти|вход|номер телефона|email или телефон",
    re.IGNORECASE,
)
SUBSCRIBE_TEXT = re.compile(
    r"^(подписаться|добавить в друзья)$",
    re.IGNORECASE,
)
MESSAGE_TEXT = re.compile(
    r"^(сообщение|написать сообщение)$",
    re.IGNORECASE,
)


async def locator_is_visible(locator) -> bool:
    try:
        return await locator.first.is_visible()
    except Exception:
        return False


async def detect_blocking_state(page: Page) -> str | None:
    body_text = await page.locator("body").inner_text(timeout=10_000)
    url = page.url.lower()
    captcha_locator = page.locator(
        'iframe[src*="captcha" i], '
        '[class*="captcha" i], '
        '[id*="captcha" i], '
        'input[name*="captcha" i]'
    )

    if (
        "captcha" in url
        or CAPTCHA_TEXT.search(body_text)
        or await locator_is_visible(captcha_locator)
    ):
        return "captcha"

    password = page.locator('input[type="password"]')
    login_form = page.locator(
        'form[action*="login" i], input[name="email"], input[name="phone"]'
    )
    if (
        "login" in url
        or await locator_is_visible(password)
        or await locator_is_visible(login_form)
        or LOGIN_TEXT.search(body_text[:1500])
    ):
        return "session_expired"
    return None


async def find_message_control(page: Page):
    button = page.get_by_role("button", name=MESSAGE_TEXT)
    if await locator_is_visible(button):
        return button.first

    link = page.get_by_role("link", name=MESSAGE_TEXT)
    if await locator_is_visible(link):
        return link.first

    by_href = page.locator('a[href^="/write"], a[href*="/write"]')
    if await locator_is_visible(by_href):
        return by_href.first
    return None


def _screenshot_path(directory: Path, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"vk-{label}-{stamp}.png"


async def _raise_if_blocked(page: Page, screenshot_dir: Path) -> None:
    state = await detect_blocking_state(page)
    if state == "captcha":
        screenshot = _screenshot_path(screenshot_dir, "captcha")
        await page.screenshot(path=str(screenshot), full_page=True)
        raise VkCaptchaRequired(str(screenshot))
    if state == "session_expired":
        raise VkSessionExpired("VK-сессия истекла, обновите vk_auth.json")


async def prepare_profile_page(
    page: Page,
    url: str,
    *,
    subscribe_if_available: bool = True,
    screenshot_dir: Path = Path("/tmp"),
):
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(2_000)
    await _raise_if_blocked(page, screenshot_dir)

    subscribe = page.get_by_role("button", name=SUBSCRIBE_TEXT)
    if subscribe_if_available and await locator_is_visible(subscribe):
        await subscribe.first.click(timeout=10_000)
        await page.wait_for_timeout(2_000)
        await _raise_if_blocked(page, screenshot_dir)

    message_control = await find_message_control(page)
    if message_control is None:
        screenshot = _screenshot_path(screenshot_dir, "message-control-missing")
        await page.screenshot(path=str(screenshot), full_page=True)
        raise RuntimeError(
            "VK не предоставил кнопку отправки сообщения; возможно, сообщения "
            "закрыты, профиль уже находится в другом состоянии или изменилась "
            f"разметка. Screenshot: {screenshot}"
        )
    return message_control


async def send_message_on_page(
    page: Page,
    url: str,
    message: str,
    *,
    subscribe_if_available: bool = True,
    screenshot_dir: Path = Path("/tmp"),
) -> dict[str, str | bool]:
    message_control = await prepare_profile_page(
        page,
        url,
        subscribe_if_available=subscribe_if_available,
        screenshot_dir=screenshot_dir,
    )
    await message_control.click(timeout=10_000)
    await _raise_if_blocked(page, screenshot_dir)

    editor = page.locator(
        '[contenteditable="true"][role="textbox"], '
        '[contenteditable="true"], textarea'
    ).last
    await editor.wait_for(state="visible", timeout=15_000)
    await editor.fill(message)

    send_button = page.get_by_role(
        "button",
        name=re.compile(r"^отправить", re.IGNORECASE),
    )
    if await locator_is_visible(send_button):
        await send_button.first.click(timeout=10_000)
    else:
        await editor.press("Enter")

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
        remaining = ""

    if remaining:
        screenshot = _screenshot_path(screenshot_dir, "send-not-confirmed")
        await page.screenshot(path=str(screenshot), full_page=True)
        raise RuntimeError(
            "VK не подтвердил отправку: редактор сообщения не очистился. "
            f"Screenshot: {screenshot}"
        )
    return {"success": True, "message_id": ""}


class VkService:
    @staticmethod
    async def send_message_playwright(
        url: str,
        message: str,
    ) -> dict[str, str | bool]:
        auth = os.getenv("AUTH")
        if not auth:
            raise Exception(
                "Укажите Bright Data Browser API credentials в переменной AUTH "
                "в формате USERNAME:PASSWORD."
            )

        endpoint_url = f"wss://{auth}@brd.superproxy.io:9222"

        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(endpoint_url)
            browser.new_context(storage_state="vk_auth.json")
            try:
                page = await browser.new_page()
                client = await page.context.new_cdp_session(page)

                # Автосолвер капчи включен по умолчанию.
                # Если нужно явно управлять им, можно раскомментировать:
                # await client.send("Captcha.setAutoSolve", {"autoSolve": True})

                result = await send_message_on_page(page, url, message)
                return result
            finally:
                await browser.close()
