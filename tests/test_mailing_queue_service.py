from unittest import TestCase

from worker.routing import queue_for_channel


class MailingQueueRoutingTest(TestCase):
    def test_routes_supported_channels(self) -> None:
        self.assertEqual(queue_for_channel("email"), "mailing_email")
        self.assertEqual(queue_for_channel("telegram"), "mailing_telegram")
        self.assertEqual(queue_for_channel("vk"), "mailing_vk")

    def test_defaults_to_email_queue(self) -> None:
        self.assertEqual(queue_for_channel(None), "mailing_email")
        self.assertEqual(queue_for_channel("unknown"), "mailing_email")
