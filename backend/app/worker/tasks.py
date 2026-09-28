"""Background email delivery task."""

import logging
import uuid

from app.db import database
from app.services.email_delivery import AttemptResult, attempt_delivery, retry_delay_seconds
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def session_factory():
    """Database session for the worker (tests replace this to use the test database)."""
    return database.SessionLocal()


@celery_app.task(bind=True, name="email.send", max_retries=None)
def send_email_task(self, history_id: str) -> str:
    """Deliver one queued email. Retries transient failures with exponential backoff;
    the number of attempts is bounded by the company's max_send_retries preference."""
    db = session_factory()
    try:
        outcome = attempt_delivery(db, uuid.UUID(history_id))
    finally:
        db.close()

    if outcome.result == AttemptResult.RETRY:
        countdown = retry_delay_seconds(outcome.attempts)
        logger.info("Email %s: retrying in %ss (attempt %s)", history_id, countdown, outcome.attempts)
        raise self.retry(countdown=countdown)
    return outcome.result.value
