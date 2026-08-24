"""Geofenced visit check-in/check-out — the ground truth that a professional actually
showed up at the patient's address, used to unlock payout and prompt the review flow.
"""

import json
import uuid
from datetime import UTC, datetime

from geoalchemy2.elements import WKTElement
from geoalchemy2.functions import ST_Distance
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import BookingStatus
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.models.booking import Booking, BookingVisit
from app.repositories.booking_repo import BookingRepository
from app.schemas.booking import VisitCheckInIn, VisitCheckOutIn
from app.services.booking_service import BookingService


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
        current_point = WKTElement(f"POINT({payload.longitude} {payload.latitude})", srid=4326)

        distance_result = await self.session.execute(
            select(ST_Distance(booking.service_location, current_point))
        )
        distance_meters = distance_result.scalar_one()
        if distance_meters > settings.VISIT_CHECKIN_GEOFENCE_METERS:
            raise ValidationAppError(
                f"You are {int(distance_meters)}m from the patient's address — move within "
                f"{settings.VISIT_CHECKIN_GEOFENCE_METERS}m to check in."
            )

        visit = await self._get_or_create_visit(booking_id)
        visit.checked_in_at = datetime.now(UTC)
        visit.checked_in_location = current_point
        visit.checked_in_distance_meters = int(distance_meters)

        await self.booking_service.transition_status(booking, BookingStatus.IN_PROGRESS)
        return booking

    async def check_out(
        self, booking_id: uuid.UUID, professional_id: uuid.UUID, payload: VisitCheckOutIn
    ) -> Booking:
        booking = await self._get_booking_for_professional(booking_id, professional_id)
        visit = await self._get_or_create_visit(booking_id)
        if visit.checked_in_at is None:
            raise ValidationAppError("Cannot check out before checking in.")

        visit.checked_out_at = datetime.now(UTC)
        visit.checked_out_location = WKTElement(
            f"POINT({payload.longitude} {payload.latitude})", srid=4326
        )
        if payload.care_note is not None:
            visit.visit_summary_notes = payload.care_note.notes
            if payload.care_note.vitals is not None:
                visit.vitals_recorded = json.dumps(
                    payload.care_note.vitals.model_dump(exclude_none=True)
                )
        visit.proof_of_visit_photo_url = payload.proof_of_visit_photo_url

        await self.booking_service.transition_status(booking, BookingStatus.COMPLETED)
        return booking
