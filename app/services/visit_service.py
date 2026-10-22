"""Visit progress for the assigned professional: (optional) en-route, check-in to start the
visit, check-out to complete it.

Check-in can be geofenced — the professional's live location must be within
VISIT_CHECKIN_GEOFENCE_METERS of the patient's address — when VISIT_GEOFENCE_ENABLED is on.
It's off for the web prototype, where "Start visit" is a plain button.
"""

import uuid
from datetime import UTC, datetime, timedelta

from geoalchemy2.elements import WKTElement
from geoalchemy2.functions import ST_Distance
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import BookingStatus
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.models.booking import Booking, BookingVisit
from app.models.professional import ProfessionalProfile
from app.repositories.booking_repo import BookingRepository
from app.schemas.booking import VisitCheckInIn, VisitCheckOutIn
from app.services.booking_service import BookingService

# How early before the scheduled start a visit may be started — stops a mis-tap on next
# week's booking from marking it in progress today.
EARLY_START_WINDOW = timedelta(hours=2)
STARTABLE_STATUSES = frozenset(
    {BookingStatus.ASSIGNED, BookingStatus.CONFIRMED, BookingStatus.EN_ROUTE}
)


def _point(latitude: float, longitude: float) -> WKTElement:
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


class VisitService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.bookings = BookingRepository(session)
        self.booking_service = BookingService(session)

    async def _get_booking_for_professional(
        self, booking_id: uuid.UUID, professional_id: uuid.UUID
    ) -> Booking:
        booking = await self.bookings.get(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        if booking.professional_id != professional_id:
            raise ForbiddenError("This booking is not assigned to you.")
        return booking

    async def _get_or_create_visit(self, booking_id: uuid.UUID) -> BookingVisit:
        result = await self.session.execute(
            select(BookingVisit).where(BookingVisit.booking_id == booking_id)
        )
        visit = result.scalar_one_or_none()
        if visit is None:
            visit = BookingVisit(booking_id=booking_id)
            self.session.add(visit)
            await self.session.flush()
        return visit

    async def mark_en_route(self, booking_id: uuid.UUID, professional_id: uuid.UUID) -> Booking:
        booking = await self._get_booking_for_professional(booking_id, professional_id)
        visit = await self._get_or_create_visit(booking_id)
        visit.en_route_at = datetime.now(UTC)
        await self.booking_service.transition_status(booking, BookingStatus.EN_ROUTE)
        return booking

    async def check_in(
        self, booking_id: uuid.UUID, professional_id: uuid.UUID, payload: VisitCheckInIn
    ) -> Booking:
        booking = await self._get_booking_for_professional(booking_id, professional_id)
        if booking.status not in STARTABLE_STATUSES:
            raise ValidationAppError(f"A {booking.status} visit can't be started.")
        now = datetime.now(UTC)
        if booking.scheduled_start_at.replace(tzinfo=UTC) - now > EARLY_START_WINDOW:
            raise ValidationAppError(
                "This visit can be started up to 2 hours before its scheduled time."
            )

        has_location = payload.latitude is not None and payload.longitude is not None
        visit = await self._get_or_create_visit(booking_id)
        if has_location:
            current_point = _point(payload.latitude, payload.longitude)  # type: ignore[arg-type]
            distance_result = await self.session.execute(
                select(ST_Distance(booking.service_location, current_point))
            )
            distance_meters = distance_result.scalar_one()
            if (
                settings.VISIT_GEOFENCE_ENABLED
                and distance_meters > settings.VISIT_CHECKIN_GEOFENCE_METERS
            ):
                raise ValidationAppError(
                    f"You are {int(distance_meters)}m from the patient's address — move within "
                    f"{settings.VISIT_CHECKIN_GEOFENCE_METERS}m to check in."
                )
            visit.checked_in_location = current_point
            visit.checked_in_distance_meters = int(distance_meters)
        elif settings.VISIT_GEOFENCE_ENABLED:
            raise ValidationAppError("Share your location to start the visit.")

        visit.checked_in_at = now
        await self.booking_service.transition_status(booking, BookingStatus.IN_PROGRESS)
        return booking

    async def check_out(
        self, booking_id: uuid.UUID, professional_id: uuid.UUID, payload: VisitCheckOutIn
    ) -> Booking:
        booking = await self._get_booking_for_professional(booking_id, professional_id)
        if booking.status != BookingStatus.IN_PROGRESS:
            raise ValidationAppError("Start the visit before completing it.")
        visit = await self._get_or_create_visit(booking_id)

        visit.checked_out_at = datetime.now(UTC)
        if payload.latitude is not None and payload.longitude is not None:
            visit.checked_out_location = _point(payload.latitude, payload.longitude)
        visit.visit_summary_notes = payload.visit_summary_notes
        visit.vitals_recorded = payload.vitals_recorded
        visit.proof_of_visit_photo_url = payload.proof_of_visit_photo_url

        await self.booking_service.transition_status(booking, BookingStatus.COMPLETED)
        professional = await self.session.get(ProfessionalProfile, professional_id)
        if professional is not None:
            professional.total_visits_completed += 1
        await self.session.flush()
        return booking
