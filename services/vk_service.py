import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from services.logger import log
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


async def _seed_persistent_profile(
    context,
    storage_state_path: Path,
) -> None:
    """Import a legacy Playwright storage state into a new persistent profile."""
    if not storage_state_path.is_file():
        return

    state = json.loads(storage_state_path.read_text(encoding="utf-8"))
    cookies = state.get("cookies") or []
    if cookies:
        await context.add_cookies(cookies)

    origins = state.get("origins") or []
    if origins:
        init_script = """
        (states) => {
            const state = states.find(item => item.origin === location.origin);
            if (!state) return;
            for (const item of state.localStorage || []) {
                localStorage.setItem(item.name, item.value);
            }
        }
        """
        await context.add_init_script(
            script=f"({init_script})({json.dumps(origins, ensure_ascii=False)})"
        )


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


async def _raise_if_blocked(page: Page, screenshot_dir: Path) -> True:
    state = await detect_blocking_state(page)
    if state == "captcha":
        screenshot = _screenshot_path(screenshot_dir, "captcha")
        await page.get_by_text("Продолжить").click()
        await asyncio.sleep(2)
        await page.screenshot(path=str(screenshot), full_page=True)
        log.error("Captcha required, screenshot: ", str(screenshot))
        return True
    if state == "session_expired":
        raise VkSessionExpired(
            "VK-сессия истекла, обновите vk_auth.json"
        )
    return True


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
        # VK may replace or remove the editor after a successful send.
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
        async with async_playwright() as playwright:
            headless = (
                os.getenv("VK_PLAYWRIGHT_HEADLESS", "true").lower() != "false"
            )
            profile_path = Path(
                os.getenv(
                    "VK_PLAYWRIGHT_PROFILE",
                    "/app/vk-profile",
                )
            )
            storage_state_path = Path(
                os.getenv(
                    "VK_PLAYWRIGHT_STORAGE_STATE",
                    "vk_auth.json",
                )
            )
            profile_path.mkdir(parents=True, exist_ok=True)
            initialized_marker = profile_path / ".initialized"

            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_path),
                headless=headless,
            )
            try:
                if not initialized_marker.exists():
                    await _seed_persistent_profile(
                        context,
                        storage_state_path,
                    )
                    initialized_marker.touch()

                page = (
                    context.pages[0]
                    if context.pages
                    else await context.new_page()
                )
                return await send_message_on_page(page, url, message)
            finally:
                await context.close()
