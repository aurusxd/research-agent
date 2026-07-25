from types import SimpleNamespace
from unittest import TestCase

from services.delivery_channel_resolver import (
    DeliveryChannelResolutionError,
    resolve_delivery_channel,
)


def contact(**overrides):
    data = {
        "preferred_channel": "email",
        "email": "museum@example.org",
        "recipient_address": None,
        "contact_form_url": None,
        "vk_url": None,
        "recipient_external_id": None,
        "ok_url": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class DeliveryChannelResolverTest(TestCase):
    def test_preserves_agent_selected_contact_form(self) -> None:
        item = contact(
            preferred_channel="contact_form",
            contact_form_url="https://example.org/contact",
        )
        self.assertEqual(resolve_delivery_channel(item), "contact_form")

    def test_preserves_agent_selected_ok(self) -> None:
        item = contact(
            preferred_channel="ok.ru",
            ok_url="https://ok.ru/group/example",
        )
        self.assertEqual(resolve_delivery_channel(item), "ok")

    def test_does_not_replace_missing_agent_choice_with_email(self) -> None:
        item = contact(preferred_channel=None)
        with self.assertRaises(DeliveryChannelResolutionError):
            resolve_delivery_channel(item)
