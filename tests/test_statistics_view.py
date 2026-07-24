from unittest import TestCase

from telegram.statistics import build_statistics_text


class StatisticsViewTest(TestCase):
    def test_builds_readable_statistics(self) -> None:
        text = build_statistics_text(
            {
                "period": "today",
                "search_runs": 2,
                "pages_found": 35,
                "contacts_found": 8,
                "pending_review": 3,
                "approved": 2,
                "rejected": 1,
                "emails_sent": 2,
                "replies": 0,
                "errors": 1,
            }
        )

        self.assertIn("Период: <b>Сегодня</b>", text)
        self.assertIn("Найдено контактов: 8", text)
        self.assertIn("Отправлено email: 2", text)
