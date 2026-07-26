"""Create a VK Playwright session through one-time manual authorization."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


VK_URL = "https://vk.com/"
VK_SESSION_COOKIES = {"remixsid", "remixsid6"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Open VK in a visible browser, wait for manual authorization and "
            "save the Playwright session used by celery-vk."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("vk_auth.json"),
        help="Storage-state output file (default: vk_auth.json)",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path("vk-profile"),
        help="Persistent Chromium profile (default: vk-profile)",
    )
    return parser.parse_args()


async def has_vk_session(context) -> bool:
    cookies = await context.cookies(["https://vk.com", "https://vk.ru"])
    return any(
        cookie.get("name") in VK_SESSION_COOKIES
        and bool(cookie.get("value"))
        for cookie in cookies
    )


async def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    profile_dir = args.profile_dir.resolve()

    output.parent.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
        )
        try:
            page = (
                context.pages[0]
                if context.pages
                else await context.new_page()
            )
            await page.goto(VK_URL, wait_until="domcontentloaded")

            print(
                "\nВойдите в VK вручную в открывшемся браузере.\n"
                "После появления ленты или профиля вернитесь в терминал "
                "и нажмите Enter.\n"
            )
            await asyncio.to_thread(input)

            if not await has_vk_session(context):
                print(
                    "VK-сессия не обнаружена. Убедитесь, что вход завершён, "
                    "и запустите скрипт ещё раз."
                )
                return 1

            state = await context.storage_state()
            temporary_output = output.with_suffix(output.suffix + ".tmp")
            temporary_output.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary_output.replace(output)

            print(f"VK storage state сохранён: {output}")
            print(f"Постоянный профиль сохранён: {profile_dir}")
            return 0
        finally:
            await context.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
