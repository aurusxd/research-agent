from unittest import TestCase

from worker.policy import is_temporary_error


class WorkerPolicyTest(TestCase):
    def test_retries_temporary_transport_errors(self) -> None:
        self.assertTrue(is_temporary_error(RuntimeError("connection timeout")))
        self.assertTrue(is_temporary_error(RuntimeError("HTTP 429")))

    def test_does_not_retry_permanent_validation_errors(self) -> None:
        self.assertFalse(
            is_temporary_error(RuntimeError("отсутствует recipient_external_id"))
        )
