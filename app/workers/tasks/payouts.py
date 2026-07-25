"""Weekly professional payout generation — triggered by Celery beat every Monday 03:00 IST."""
from datetime import UTC, datetime, timedelta

from app.services.payout_service import PayoutService
from app.workers.celery_app import celery_app
from app.workers.tasks._runner import run_with_session


@celery_app.task(name="app.workers.tasks.payouts.run_weekly_payout_generation")
def run_weekly_payout_generation() -> int:
    async def _run(session):
        period_end = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        period_start = period_end - timedelta(days=7)
        payouts = await PayoutService(session).generate_weekly_payouts(
            period_start=period_start, period_end=period_end
        )
        return len(payouts)

    return run_with_session(_run)
