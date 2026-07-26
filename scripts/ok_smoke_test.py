"""Manual smoke test that uses the production OK.ru page automation."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Page, async_playwright

# Direct execution (`python scripts/ok_smoke_test.py`) puts only /app/scripts
# on sys.path. Add the repository root so production service modules resolve.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.delivery_errors import VkCaptchaRequired, VkSessionExpired
from services.ok_service import (
    detect_blocking_state,
    find_write_control,
    send_message_on_page,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a real OK.ru Playwright smoke test.",
    )
    parser.add_argument("url", help="OK.ru profile/community URL")
    parser.add_argument(
        "--storage-state",
        type=Path,
        default=Path("ok_auth.json"),
        help="Playwright storage state (default: ok_auth.json)",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("smoke-artifacts"),
        help="Directory for screenshot, trace and report",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without a visible browser (visible by default)",
    )
    parser.add_argument(
        "--send-message",
        metavar="TEXT",
        help="Actually send this message using production service code",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30_000,
        help="Default Playwright timeout in milliseconds",
    )
    return parser.parse_args()


def validate_ok_url(value: str) -> str:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        hostname == "ok.ru" or hostname.endswith(".ok.ru")
    ):
        raise ValueError("Only https://ok.ru/... URLs are allowed")
    return value


async def page_summary(page: Page) -> dict[str, object]:
    result: dict[str, object] = {
        "url": page.url,
        "title": await page.title(),
    }
    for role, key in (("button", "buttons"), ("link", "links")):
        locator = page.get_by_role(role)
        labels: list[str] = []
        for index in range(min(await locator.count(), 50)):
            try:
                label = (await locator.nth(index).inner_text()).strip()
            except Exception:
                continue
            if label and label not in labels:
                labels.append(label[:120])
        result[key] = labels
    return result


async def run(args: argparse.Namespace) -> int:
    url = validate_ok_url(args.url)
    storage_state = args.storage_state.resolve()
    if not storage_state.is_file():
        raise FileNotFoundError(f"Storage state not found: {storage_state}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (args.artifacts_dir / f"ok-{stamp}").resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    screenshot_path = run_dir / "page.png"
    trace_path = run_dir / "trace.zip"
    report_path = run_dir / "report.json"
    report: dict[str, object] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "target_url": url,
        "headless": args.headless,
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
            if args.send_message is not None:
                await send_message_on_page(
                    page,
                    url,
                    args.send_message,
                    screenshot_dir=run_dir,
                )
                report["message_sent"] = True
            else:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=args.timeout,
                )
                await page.wait_for_timeout(2_000)
                blocking_state = await detect_blocking_state(page)
                report["blocking_state"] = blocking_state
                if blocking_state:
                    report["status"] = blocking_state
                    return 2
                write_control = await find_write_control(page)
                report["write_control_visible"] = write_control is not None
                if write_control is None:
                    report["status"] = "write_control_missing"
                    return 3
                report["message_sent"] = False

            report["page"] = await page_summary(page)
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
