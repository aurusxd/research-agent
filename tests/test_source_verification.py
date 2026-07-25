from unittest import TestCase
from unittest.mock import Mock, patch

from services.source_verification import verify_source


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
