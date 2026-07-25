from types import SimpleNamespace
from unittest import TestCase

from services.invitation_generator import (
    ensure_contact_invitation,
    ensure_invitation,
)


class InvitationGeneratorTest(TestCase):
    def test_keeps_agent_generated_message(self) -> None:
        message = "Персонализированный текст, подготовленный агентом."

        self.assertEqual(
            ensure_invitation(
                message,
                organization_name="Музей",
                category="краеведение",
                preferred_channel="email",
            ),
            message,
        )

    def test_builds_channel_aware_fallback(self) -> None:
        contact = SimpleNamespace(
            organization_name="Краеведческий музей",
            category="краеведение",
            preferred_channel="vk",
            generated_message=None,
        )

        message = ensure_contact_invitation(contact)

        self.assertIn("Краеведческий музей", message)
        self.assertIn("краеведение", message)
        self.assertNotIn("\n\n", message)
