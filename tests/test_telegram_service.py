from unittest import TestCase

from services.telegram_service import (
    TelegramConfigurationError,
    TelegramTarget,
    parse_telegram_target,
)


class TelegramTargetTest(TestCase):
    def test_parses_public_username_url(self) -> None:
        self.assertEqual(
            parse_telegram_target("https://t.me/familio_kursk"),
            TelegramTarget("public", "familio_kursk"),
        )

    def test_parses_at_username(self) -> None:
        self.assertEqual(
            parse_telegram_target("@familio_kursk"),
            TelegramTarget("public", "familio_kursk"),
        )

    def test_parses_modern_private_invite(self) -> None:
        self.assertEqual(
            parse_telegram_target("https://t.me/+Abc_123-xyz"),
            TelegramTarget("invite", "Abc_123-xyz"),
        )

    def test_parses_legacy_private_invite(self) -> None:
        self.assertEqual(
            parse_telegram_target(
                "https://telegram.me/joinchat/Abc_123-xyz"
            ),
            TelegramTarget("invite", "Abc_123-xyz"),
        )

    def test_rejects_non_telegram_url(self) -> None:
        with self.assertRaises(TelegramConfigurationError):
            parse_telegram_target("https://example.org/familio_kursk")
