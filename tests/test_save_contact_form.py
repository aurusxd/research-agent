from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from agent.tools.save_contact import save_contact


class SaveContactFormVerificationTest(IsolatedAsyncioTestCase):
    @patch("agent.tools.save_contact.ContactRepository")
    @patch("agent.tools.save_contact.verify_source")
    async def test_switches_email_page_to_email_channel(
        self,
        verify_source: Mock,
        repository_class: Mock,
    ) -> None:
        verify_source.return_value = {
            "verified": True,
            "source_url": "https://example.org/contacts",
            "final_url": "https://example.org/contacts",
            "emails": ["museum@example.org"],
            "social_links": [],
            "page_excerpt": "museum@example.org",
            "has_contact_form": False,
        }
        repository = repository_class.return_value
        repository.find_duplicate = AsyncMock(return_value=None)
        repository.create = AsyncMock(
            return_value=SimpleNamespace(id=42)
        )

        result = await save_contact(
            organization_name="Музей",
            source="https://example.org/contacts",
            relevance_score=90,
            relevance_reason="Краеведение",
            contact_form_url="https://example.org/contacts",
            preferred_channel="contact_form",
            recipient_address="https://example.org/contacts",
            generated_message=(
                "Здравствуйте! Приглашаем музей в проект «Корни»."
            ),
            session=SimpleNamespace(),
        )

        self.assertTrue(result["success"])
        saved = repository.create.await_args.args[0]
        self.assertEqual(saved["preferred_channel"], "email")
        self.assertEqual(saved["email"], "museum@example.org")
        self.assertEqual(
            saved["recipient_address"],
            "museum@example.org",
        )
        self.assertNotIn("contact_form_url", saved)

    @patch("agent.tools.save_contact.ContactRepository")
    @patch("agent.tools.save_contact.verify_source")
    async def test_rejects_page_without_form_or_email(
        self,
        verify_source: Mock,
        repository_class: Mock,
    ) -> None:
        verify_source.return_value = {
            "verified": True,
            "source_url": "https://example.org/contacts",
            "final_url": "https://example.org/contacts",
            "emails": [],
            "social_links": [],
            "page_excerpt": "Контакты организации",
            "has_contact_form": False,
        }

        result = await save_contact(
            organization_name="Музей",
            source="https://example.org/contacts",
            relevance_score=90,
            relevance_reason="Краеведение",
            contact_form_url="https://example.org/contacts",
            preferred_channel="contact_form",
            recipient_address="https://example.org/contacts",
            generated_message=(
                "Здравствуйте! Приглашаем музей в проект «Корни»."
            ),
            session=SimpleNamespace(),
        )

        self.assertFalse(result["success"])
        self.assertIn("не содержит интерактивной формы", result["message"])
        repository_class.return_value.create.assert_not_called()
