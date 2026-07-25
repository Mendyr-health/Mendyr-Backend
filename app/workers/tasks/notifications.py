"""Async/retriable notification dispatch — offloads slow push/SMS sends off the request path."""
import uuid

from app.services.notification_service import NotificationService
from app.workers.celery_app import celery_app
from app.workers.tasks._runner import run_with_session


@celery_app.task(name="app.workers.tasks.notifications.send_push", bind=True, max_retries=3)
def send_push(self, user_id: str, title: str, body: str, data: dict | None = None) -> None:
    async def _run(session):
        await NotificationService(session).push_to_user(
            uuid.UUID(user_id), title=title, body=body, data=data
        )

    try:
        run_with_session(_run)
    except Exception as exc:  # noqa: BLE001 — retry on any transient failure (network, DB)
        raise self.retry(exc=exc, countdown=2**self.request.retries) from exc
