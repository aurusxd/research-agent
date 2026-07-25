import os
from unittest import TestCase, skipUnless


@skipUnless(
    os.getenv("RUN_INTEGRATION_TESTS") == "1",
    "set RUN_INTEGRATION_TESTS=1 inside Docker Compose",
)
class CeleryInfrastructureIntegrationTest(TestCase):
    def test_redis_and_required_workers_are_available(self) -> None:
        from redis import Redis
        from worker.celery_app import celery_app

        redis = Redis.from_url(
            os.getenv("REDIS_URL", "redis://redis:6379/0")
        )
        self.assertTrue(redis.ping())

        queues_by_worker = celery_app.control.inspect(
            timeout=5
        ).active_queues() or {}
        queue_names = {
            queue["name"]
            for queues in queues_by_worker.values()
            for queue in queues
        }
        self.assertTrue(
            {"mailing_email", "mailing_telegram", "mailing_vk"}
            <= queue_names
        )
