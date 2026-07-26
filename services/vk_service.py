import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

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

    password_visible = await locator_is_visible(
        page.locator('input[type="password"]')
    )
    login_form_visible = await locator_is_visible(
        page.locator(
            'form[action*="login" i], '
            'form:has(input[name="email"]):has(input[type="password"]), '
            'form:has(input[name="phone"]):has(input[type="password"])'
        )
    )
    if _looks_like_login_page(
        url,
        body_text,
        password_visible=password_visible,
        login_form_visible=login_form_visible,
    ):
        return "session_expired"
    return None


def _looks_like_login_page(
    url: str,
    body_text: str,
    *,
    password_visible: bool,
    login_form_visible: bool,
) -> bool:
    parsed = urlparse(url.lower())
    login_url = (
        parsed.hostname in {"id.vk.com", "login.vk.com"}
        or parsed.path.rstrip("/") in {"/login", "/auth"}
        or parsed.path.startswith("/login/")
    )
    if login_url or password_visible:
        return True
    # Text such as "Войти" can be present in VK navigation or a transient
    # shell. It is only evidence when a real visible login form also exists.
    return bool(login_form_visible and LOGIN_TEXT.search(body_text[:3000]))


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


async def _find_chat_editor(page: Page):
    """Return the editor of the opened messenger, never a wall comment field."""
    selectors = (
        '[contenteditable="true"][data-placeholder="Сообщение"]',
        '[contenteditable="true"][aria-label="Сообщение"]',
        'textarea[placeholder="Сообщение"]',
        'input[placeholder="Сообщение"]',
        '[contenteditable="true"][data-placeholder*="сообщен" i]',
        '[contenteditable="true"][aria-label*="сообщен" i]',
        'textarea[placeholder*="сообщен" i]',
    )
    for selector in selectors:
        candidates = page.locator(selector)
        for index in range(await candidates.count()):
            candidate = candidates.nth(index)
            if await locator_is_visible(candidate):
                return candidate
    return None


async def _new_non_editor_message_is_visible(
    matching_messages,
    matching_count_before: int,
) -> bool:
    matching_count_after = await matching_messages.count()
    for index in range(matching_count_before, matching_count_after):
        candidate = matching_messages.nth(index)
        try:
            if not await candidate.is_visible():
                continue
            belongs_to_editor = await candidate.evaluate(
                """element => Boolean(
                    element.closest('[contenteditable="true"], textarea, input')
                )"""
            )
            if not belongs_to_editor:
                return True
        except Exception:
            continue
    return False


async def _find_chat_surface(page: Page, editor):
    chat_window = editor.locator(
        'xpath=ancestor::*[@id="FCWindow"][1]'
    )
    if await locator_is_visible(chat_window):
        return chat_window

    selectors = (
        '[role="list"][aria-label="Сообщения"]',
        '[role="log"]',
    )
    for selector in selectors:
        candidates = page.locator(selector)
        for index in range(await candidates.count()):
            candidate = candidates.nth(index)
            if await locator_is_visible(candidate):
                return candidate
    return None


def _screenshot_path(directory: Path, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"vk-{label}-{stamp}.png"


async def _raise_if_blocked(page: Page, screenshot_dir: Path) -> None:
    state = await detect_blocking_state(page)
    if state == "session_expired":
        await page.wait_for_timeout(2_000)
        state = await detect_blocking_state(page)
        if state == "session_expired":
            suspected = _screenshot_path(
                screenshot_dir,
                "session-suspected",
            )
            await page.screenshot(path=str(suspected), full_page=True)
            await page.reload(
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await page.wait_for_timeout(3_000)
            state = await detect_blocking_state(page)
            if state == "session_expired":
                expired = _screenshot_path(
                    screenshot_dir,
                    "session-expired",
                )
                await page.screenshot(path=str(expired), full_page=True)
                raise VkSessionExpired(
                    "VK-сессия подтверждённо истекла после повторной "
                    "проверки и перезагрузки. Обновите persistent-профиль "
                    f"vk-profile (при необходимости заново создайте "
                    f"vk_auth.json). Screenshot: {expired}"
                )
        if state is None:
            return
    if state != "captcha":
        return

    screenshot = _screenshot_path(screenshot_dir, "captcha-detected")
    await page.screenshot(path=str(screenshot), full_page=True)

    continue_button = page.get_by_text("Продолжить", exact=True)
    if await locator_is_visible(continue_button):
        await continue_button.first.click(timeout=10_000)
        await page.wait_for_timeout(2_000)

    wait_seconds = max(
        0,
        min(
            600,
            int(os.getenv("VK_CAPTCHA_WAIT_SECONDS", "180")),
        ),
    )
    deadline = asyncio.get_running_loop().time() + wait_seconds

    while asyncio.get_running_loop().time() < deadline:
        await page.wait_for_timeout(2_000)
        state = await detect_blocking_state(page)

        if state == "session_expired":
            await _raise_if_blocked(page, screenshot_dir)
            return
        if state != "captcha":
            # Allow VK to finish redirects and restore the profile UI.
            await page.wait_for_timeout(1_000)
            return

    timeout_screenshot = _screenshot_path(
        screenshot_dir,
        "captcha-timeout",
    )
    await page.screenshot(path=str(timeout_screenshot), full_page=True)
    raise VkCaptchaRequired(str(timeout_screenshot))


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

    editor = None
    editor_deadline = asyncio.get_running_loop().time() + 15
    while asyncio.get_running_loop().time() < editor_deadline:
        editor = await _find_chat_editor(page)
        if editor is not None:
            break
        await page.wait_for_timeout(250)
    if editor is None:
        screenshot = _screenshot_path(
            screenshot_dir,
            "chat-editor-missing",
        )
        await page.screenshot(path=str(screenshot), full_page=True)
        raise RuntimeError(
            "VK открыл окно сообщения, но редактор чата не найден. "
            f"Screenshot: {screenshot}"
        )

    chat_surface = await _find_chat_surface(page, editor)
    if chat_surface is None:
        screenshot = _screenshot_path(
            screenshot_dir,
            "chat-surface-missing",
        )
        await page.screenshot(path=str(screenshot), full_page=True)
        raise RuntimeError(
            "VK открыл редактор, но контейнер нужного чата не найден. "
            f"Screenshot: {screenshot}"
        )

    # For a brand-new conversation VK does not render the message-history
    # list until the first message is sent. Scope to the chat window itself;
    # editor descendants are explicitly excluded during confirmation.
    matching_messages = chat_surface.get_by_text(message, exact=True)
    matching_count_before = await matching_messages.count()
    await editor.fill(message)

    # Pressing Enter on the selected chat editor is safer than using a global
    # "Send" button: a community page can contain many comment send buttons.
    await editor.press("Enter")

    await _raise_if_blocked(page, screenshot_dir)

    confirmation_deadline = asyncio.get_running_loop().time() + 15
    send_confirmed = False
    while asyncio.get_running_loop().time() < confirmation_deadline:
        editor_empty = False
        try:
            if await editor.count() == 0:
                editor_empty = True
            else:
                tag_name = await editor.evaluate(
                    "(element) => element.tagName.toLowerCase()"
                )
                editor_value = (
                    await editor.input_value()
                    if tag_name in {"input", "textarea"}
                    else await editor.inner_text()
                )
                editor_empty = not editor_value.strip()
        except Exception:
            # A replaced editor is acceptable only if the sent message is also
            # visible in the conversation history.
            editor_empty = True

        new_message_visible = await _new_non_editor_message_is_visible(
            matching_messages,
            matching_count_before,
        )

        if editor_empty and new_message_visible:
            send_confirmed = True
            break
        await page.wait_for_timeout(500)

    if not send_confirmed:
        screenshot = _screenshot_path(
            screenshot_dir,
            "send-not-confirmed",
        )
        await page.screenshot(path=str(screenshot), full_page=True)
        raise RuntimeError(
            "VK не подтвердил отправку: редактор не очистился или новое "
            "исходящее сообщение не появилось в истории диалога. "
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
                screenshot_dir = Path(
                    os.getenv(
                        "VK_SCREENSHOT_DIR",
                        "/app/smoke-artifacts",
                    )
                )
                return await send_message_on_page(
                    page,
                    url,
                    message,
                    screenshot_dir=screenshot_dir,
                )
            finally:
                await context.close()
