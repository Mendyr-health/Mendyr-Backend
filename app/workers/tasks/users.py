"""Background worker tasks for user maintenance (e.g. bulk cleanup/purge)."""

from __future__ import annotations

from typing import Sequence

from app.services.user_cleanup_service import UserCleanupService
from app.workers.celery_app import celery_app
from app.workers.tasks._runner import run_with_session


@celery_app.task(name="app.workers.tasks.users.delete_users_job")
def delete_users_job(
    identifiers: str | Sequence[str],
    *,
    dry_run: bool = False,
) -> dict:
    """Purge specified users and all their referencing data from every table.

    Accepts a comma-separated string (e.g. "alice@example.com, bob@example.com, <uuid>")
    or a list/sequence of identifiers.
    """

    async def _run(session):
        service = UserCleanupService(session)
        summary = await service.delete_users(identifiers, dry_run=dry_run)
        return summary.to_dict()

    return run_with_session(_run)

