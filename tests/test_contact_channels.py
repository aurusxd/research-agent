from unittest import TestCase

from pydantic import ValidationError

from schemas.save_contact_schema import SaveContactToolArgs
from services.contact_channels import has_usable_contact_channel


def _tool_args(**overrides):
    values = {
        "organization_name": "Краеведческий музей",
        "source": "https://example.org/museum",
        "relevance_score": 90,
        "relevance_reason": "Региональная история",
        "generated_message": "Здравствуйте! Приглашаем вас в проект «Корни».",
    }
    values.update(overrides)
    return values


class ContactChannelValidationTest(TestCase):
    def test_rejects_contact_without_communication_channel(self) -> None:
        with self.assertRaises(ValidationError):
            SaveContactToolArgs(
                **_tool_args(
                    website="https://example.org",
                    youtube_url="https://youtube.com/example",
                )
            )

    def test_accepts_each_supported_direct_channel(self) -> None:
        for field, value in {
            "email": "museum@example.org",
            "contact_form_url": "https://example.org/contact",
            "vk_url": "https://vk.com/museum",
            "telegram_url": "https://t.me/museum",
            "ok_url": "https://ok.ru/group/example",
        }.items():
            with self.subTest(field=field):
                item = SaveContactToolArgs(
                    **_tool_args(**{field: value})
                )
                self.assertTrue(has_usable_contact_channel(item))

    def test_recipient_address_requires_supported_channel(self) -> None:
        with self.assertRaises(ValidationError):
            SaveContactToolArgs(
                **_tool_args(recipient_address="somewhere")
            )

        item = SaveContactToolArgs(
            **_tool_args(
                preferred_channel="vk",
                recipient_address="https://vk.com/museum",
            )
        )
        self.assertTrue(has_usable_contact_channel(item))

    def test_phone_alone_is_not_supported_delivery_channel(self) -> None:
        with self.assertRaises(ValidationError):
            SaveContactToolArgs(
                **_tool_args(phone="+7 999 123-45-67")
            )
