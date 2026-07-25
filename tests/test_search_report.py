from unittest import TestCase

from worker.tasks import _build_search_report


class SearchReportTest(TestCase):
    def test_builds_completed_search_report(self) -> None:
        report = _build_search_report(
            {
                "search_run_id": 7,
                "status": "completed",
                "found_count": 18,
                "saved_count": 5,
                "duplicate_count": 3,
                "error_count": 0,
                "error_message": "",
            }
        )

        self.assertIn("Поиск #7 завершён", report)
        self.assertIn("Сохранено контактов: 5", report)
        self.assertIn("Проверка материалов", report)

    def test_includes_failure_reason(self) -> None:
        report = _build_search_report(
            {
                "search_run_id": 8,
                "status": "failed",
                "found_count": 0,
                "saved_count": 0,
                "duplicate_count": 0,
                "error_count": 1,
                "error_message": "Tavily недоступен",
            }
        )

        self.assertIn("завершился ошибкой", report)
        self.assertIn("Tavily недоступен", report)
