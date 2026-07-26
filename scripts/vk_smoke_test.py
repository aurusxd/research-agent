"""Manual smoke test for the VK browser automation.

The test is read-only by default. It opens a real VK profile using the saved
Playwright storage state, detects common blocking states and writes diagnostic
artifacts. Clicking "Subscribe" and sending a message require explicit flags.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Page, async_playwright

# Direct execution (`python scripts/vk_smoke_test.py`) puts only /app/scripts
# on sys.path. Add the repository root so production service modules resolve.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.delivery_errors import VkCaptchaRequired, VkSessionExpired
from services.vk_service import (
    SUBSCRIBE_TEXT,
    detect_blocking_state,
    find_message_control,
    locator_is_visible,
    send_message_on_page,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a real, manual VK Playwright smoke test.",
    )
    parser.add_argument("url", help="VK profile/community URL")
    parser.add_argument(
        "--storage-state",
        type=Path,
        default=Path("vk_auth.json"),
        help="Playwright storage state (default: vk_auth.json)",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("smoke-artifacts"),
        help="Directory for screenshots, trace and report",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without a visible browser (visible by default)",
    )
    parser.add_argument(
        "--subscribe",
        action="store_true",
        help='Actually click "Subscribe" if the button is present',
    )
    parser.add_argument(
        "--send-message",
        metavar="TEXT",
        help="Actually open the dialog and send this test message",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30_000,
        help="Navigation/action timeout in milliseconds",
    )
    return parser.parse_args()


def validate_vk_url(value: str) -> str:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        hostname == "vk.com" or hostname.endswith(".vk.com")
    ):
        raise ValueError("Only https://vk.com/... URLs are allowed")
    return value


async def page_summary(page: Page) -> dict[str, object]:
    buttons = page.get_by_role("button")
    links = page.get_by_role("link")
    button_labels: list[str] = []
    link_labels: list[str] = []

    for locator, target in ((buttons, button_labels), (links, link_labels)):
        count = min(await locator.count(), 50)
        for index in range(count):
            try:
                label = (await locator.nth(index).inner_text()).strip()
            except Exception:
                continue
            if label and label not in target:
                target.append(label[:120])

    return {
        "url": page.url,
        "title": await page.title(),
        "buttons": button_labels,
        "links": link_labels,
    }


async def run(args: argparse.Namespace) -> int:
    url = validate_vk_url(args.url)
    storage_state = args.storage_state.resolve()
    if not storage_state.is_file():
        raise FileNotFoundError(f"Storage state not found: {storage_state}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (args.artifacts_dir / f"vk-{stamp}").resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    screenshot_path = run_dir / "page.png"
    trace_path = run_dir / "trace.zip"
    report_path = run_dir / "report.json"

    report: dict[str, object] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "target_url": url,
        "headless": args.headless,
        "subscribe_requested": args.subscribe,
        "send_requested": args.send_message is not None,
        "status": "started",
    }

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=args.headless)
        context = await browser.new_context(storage_state=str(storage_state))
        context.set_default_timeout(args.timeout)
        await context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=args.timeout)
            await page.wait_for_timeout(2_000)

            blocking_state = await detect_blocking_state(page)
            report["page"] = await page_summary(page)
            report["blocking_state"] = blocking_state

            if blocking_state:
                report["status"] = blocking_state
                return 2

            subscribe = page.get_by_role("button", name=SUBSCRIBE_TEXT)
            report["subscribe_visible"] = await locator_is_visible(subscribe)

            if (
                args.send_message is None
                and args.subscribe
                and await locator_is_visible(subscribe)
            ):
                await subscribe.first.click()
                await page.wait_for_timeout(2_000)
                second_state = await detect_blocking_state(page)
                if second_state:
                    report["blocking_state"] = second_state
                    report["status"] = second_state
                    return 2
                report["subscribe_clicked"] = True
            else:
                report["subscribe_clicked"] = False

            message_control = await find_message_control(page)
            report["message_control_visible"] = message_control is not None

            if args.send_message is not None:
                await send_message_on_page(
                    page,
                    url,
                    args.send_message,
                    subscribe_if_available=True,
                    screenshot_dir=run_dir,
                )
                report["message_sent"] = True
            else:
                report["message_sent"] = False

            report["status"] = "ok"
            return 0
        except VkCaptchaRequired as error:
            report["status"] = "captcha"
            report["error"] = str(error)
            return 2
        except VkSessionExpired as error:
            report["status"] = "session_expired"
            report["error"] = str(error)
            return 2
        except Exception as error:
            report["status"] = "error"
            report["error_type"] = type(error).__name__
            report["error"] = str(error)
            return 1
        finally:
            try:
                await page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception as screenshot_error:
                report["screenshot_error"] = str(screenshot_error)
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            report["screenshot"] = str(screenshot_path)
            report["trace"] = str(trace_path)
            await context.tracing.stop(path=str(trace_path))
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            await browser.close()
            print(json.dumps(report, ensure_ascii=False, indent=2))
            print(f"\nArtifacts: {run_dir}")


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run(args))
    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 64


if __name__ == "__main__":
    raise SystemExit(main())
