import os

from celery import Celery


celery_app = Celery(
    "vkorni",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
    include=["worker.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=os.getenv("MAILING_TIMEZONE", "Asia/Novosibirsk"),
    enable_utc=True,
    task_annotations={
        "worker.tasks.send_approved_contact": {
            "rate_limit": os.getenv("MAILING_RATE_LIMIT", "2/m"),
        }
    },
)
