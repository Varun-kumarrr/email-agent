"""Celery application for background email delivery (broker: Redis).

Start a worker (from backend/):

    celery -A app.worker.celery_app worker --loglevel=info -Q email
    # on Windows add:  --pool=solo

The database (not a Celery result backend) is the source of truth for delivery
status, so results are not stored.
"""

from celery import Celery

from app.core.config import celery_broker_url, settings

celery_app = Celery("email_agent", broker=celery_broker_url(settings), include=["app.worker.tasks"])

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_default_queue="email",
    # At-most-once hand-off: the message is acknowledged when a worker receives it.
    # Together with the row lock/status check this prevents duplicate sends.
    task_acks_late=False,
    worker_prefetch_multiplier=1,
    task_time_limit=120,
    task_soft_time_limit=90,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    worker_hijack_root_logger=False,
    timezone="UTC",
)
