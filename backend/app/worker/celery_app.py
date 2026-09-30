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
    # Fail fast when the broker is down: the API returns 503 "queue unavailable" within a few
    # seconds instead of ~20 s (defaults: 4 s connect timeout x 4 publish attempts). One retry
    # still absorbs a momentary blip; the broker is expected on the same network.
    broker_connection_timeout=2,
    task_publish_retry_policy={"max_retries": 1, "interval_start": 0, "interval_step": 0.5, "interval_max": 0.5},
    # socket timeouts bound every Redis call, so a hung (not just stopped) Redis cannot block a
    # request forever; 5 s stays above the worker's 1 s BRPOP poll.
    broker_transport_options={"visibility_timeout": 3600, "socket_connect_timeout": 2, "socket_timeout": 5},
    worker_hijack_root_logger=False,
    timezone="UTC",
)


def broker_reachable(timeout: float = 1.0, url: str | None = None) -> bool:
    """Cheap broker check for /health: a Redis PING with connect *and* read timeouts, so a hung
    Redis cannot block the request (DNS resolution time is outside the application's control)."""
    url = url or celery_broker_url(settings)
    try:
        if url.startswith(("redis://", "rediss://")):
            import redis

            client = redis.Redis.from_url(url, socket_connect_timeout=timeout, socket_timeout=timeout)
            try:
                return bool(client.ping())
            finally:
                client.close()
        with celery_app.connection_for_write(url) as conn:  # other transports (e.g. memory:// in tests)
            conn.ensure_connection(max_retries=0, timeout=timeout)
        return True
    except Exception:
        return False
