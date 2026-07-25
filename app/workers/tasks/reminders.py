"""Push reminders for upcoming visits — runs every 15 minutes via Celery beat."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.constants import BookingStatus
from app.models.booking import Booking
from app.services.notification_service import NotificationService
from app.workers.celery_app import celery_app
from app.workers.tasks._runner import run_with_session

REMINDER_WINDOW_MINUTES = 30


@celery_app.task(name="app.workers.tasks.reminders.send_upcoming_visit_reminders")
def send_upcoming_visit_reminders() -> int:
    async def _run(session):
        now = datetime.now(UTC)
        window_end = now + timedelta(minutes=REMINDER_WINDOW_MINUTES)
        result = await session.execute(
            select(Booking).where(
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.ASSIGNED]),
                Booking.scheduled_start_at >= now,
                Booking.scheduled_start_at <= window_end,
            )
        )
        bookings = list(result.scalars().all())
        notifications = NotificationService(session)
        for booking in bookings:
            await notifications.notify_booking_status(
                booking,
                title="Upcoming visit",
                body=f"Your {booking.service_name_snapshot} visit starts soon.",
            )
        return len(bookings)

    return run_with_session(_run)
