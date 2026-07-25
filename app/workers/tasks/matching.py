"""Sweeps bookings stuck in SEARCHING with fully-expired offer rounds and escalates dispatch."""
from sqlalchemy import select

from app.core.constants import BookingStatus
from app.models.booking import Booking
from app.services.matching_service import MatchingService
from app.workers.celery_app import celery_app
from app.workers.tasks._runner import run_with_session


@celery_app.task(name="app.workers.tasks.matching.sweep_expired_offers")
def sweep_expired_offers() -> int:
    async def _run(session):
        result = await session.execute(
            select(Booking.id).where(Booking.status == BookingStatus.SEARCHING)
        )
        booking_ids = [row[0] for row in result.all()]
        matching = MatchingService(session)
        for booking_id in booking_ids:
            await matching.expire_and_escalate(booking_id)
        return len(booking_ids)

    return run_with_session(_run)
