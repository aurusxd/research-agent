from unittest import TestCase
from unittest.mock import Mock, patch

from services.source_verification import (
    has_interactive_contact_form,
    verify_source,
)


class SourceVerificationTest(TestCase):
    @patch("services.source_verification.requests.get")
    def test_extracts_public_contacts(self, get: Mock) -> None:
        response = Mock()
        response.text = (
            "<html>Почта: museum@example.org "
            '<a href="https://vk.com/example">VK</a></html>'
        )
        response.url = "https://museum.example.org/contacts"
        response.raise_for_status.return_value = None
        get.return_value = response

        result = verify_source("https://museum.example.org")

        self.assertTrue(result["verified"])
        self.assertIn("museum@example.org", result["emails"])
        self.assertIn("https://vk.com/example", result["social_links"])

    @patch("services.source_verification.requests.get")
    def test_marks_unavailable_source_unverified(self, get: Mock) -> None:
        import requests

        get.side_effect = requests.Timeout("timeout")
        result = verify_source("https://museum.example.org")
        self.assertFalse(result["verified"])

    def test_email_page_is_not_mistaken_for_contact_form(self) -> None:
        html = (
            "<html><body><h1>Контакты</h1>"
            "<p>Напишите нам: museum@example.org</p>"
            "</body></html>"
        )
        self.assertFalse(has_interactive_contact_form(html))

    def test_requires_message_field_and_submit_inside_form(self) -> None:
        html = """
        <form action="/feedback" method="post">
            <input type="email" name="email">
            <textarea name="message"></textarea>
            <button type="submit">Отправить</button>
        </form>
        """
        self.assertTrue(has_interactive_contact_form(html))

    def test_email_subscription_form_is_not_contact_form(self) -> None:
        html = """
        <form action="/subscribe">
            <input type="email" name="email">
            <button type="submit">Подписаться</button>
        </form>
        """
        self.assertFalse(has_interactive_contact_form(html))

    @patch("services.source_verification.requests.get")
    def test_verification_reports_form_capability(self, get: Mock) -> None:
        response = Mock()
        response.text = """
        <form>
            <textarea name="question"></textarea>
            <input type="submit" value="Отправить">
        </form>
        """
        response.url = "https://museum.example.org/feedback"
        response.raise_for_status.return_value = None
        get.return_value = response

        result = verify_source(response.url)

        self.assertTrue(result["has_contact_form"])
