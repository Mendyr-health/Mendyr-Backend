"""Booking state machine: quoting, creation, status transitions and cancellation.

Deliberately does NOT import `MatchingService` — that would create a service-layer import
cycle (matching needs to read/transition bookings too). Whoever drives the booking forward
(the payment webhook, an API endpoint) is responsible for calling
`MatchingService.start_dispatch(booking.id)` once a booking reaches a payable/confirmed state.
"""

import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import BookingStatus, BookingType
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.models.address import Address
from app.models.booking import Booking, BookingStatusHistory
from app.models.service import Service
from app.repositories.booking_repo import BookingRepository
from app.schemas.booking import BookingCreateIn
from app.services.pricing_service import PriceBreakdown, PricingService

VALID_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.CREATED: {BookingStatus.SEARCHING, BookingStatus.CANCELLED, BookingStatus.FAILED},
    BookingStatus.SEARCHING: {
        BookingStatus.ASSIGNED,
        BookingStatus.CANCELLED,
        BookingStatus.FAILED,
    },
    BookingStatus.ASSIGNED: {
        BookingStatus.CONFIRMED,
        BookingStatus.CANCELLED,
        BookingStatus.SEARCHING,
    },
    BookingStatus.CONFIRMED: {
        BookingStatus.EN_ROUTE,
        BookingStatus.CANCELLED,
        BookingStatus.NO_SHOW,
    },
    BookingStatus.EN_ROUTE: {
        BookingStatus.IN_PROGRESS,
        BookingStatus.CANCELLED,
        BookingStatus.NO_SHOW,
    },
    BookingStatus.IN_PROGRESS: {BookingStatus.COMPLETED},
    BookingStatus.COMPLETED: set(),
    BookingStatus.CANCELLED: set(),
    BookingStatus.NO_SHOW: set(),
    BookingStatus.FAILED: {BookingStatus.SEARCHING},
}

CODE_ALPHABET = string.ascii_uppercase + string.digits


def _generate_booking_code() -> str:
    return "MNDYR-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.bookings = BookingRepository(session)
        self.pricing = PricingService(session)

    async def transition_status(
        self,
        booking: Booking,
        to_status: BookingStatus,
        *,
        reason: str | None = None,
        changed_by_id: uuid.UUID | None = None,
    ) -> Booking:
        allowed = VALID_TRANSITIONS.get(booking.status, set())
        if to_status not in allowed:
            raise ValidationAppError(f"Cannot move booking from {booking.status} to {to_status}.")

        from_status = booking.status
        booking.status = to_status
        self.session.add(
            BookingStatusHistory(
                booking_id=booking.id,
                from_status=from_status,
                to_status=to_status,
                changed_by_id=changed_by_id,
                reason=reason,
                created_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        return booking

    async def quote(self, *, service: Service, coupon_code: str | None) -> PriceBreakdown:
        return await self.pricing.quote(
            base_price=float(service.base_price), coupon_code=coupon_code
        )

    async def create_booking(
        self, *, patient_id: uuid.UUID, service: Service, address: Address, payload: BookingCreateIn
    ) -> Booking:
        if address.user_id != patient_id:
            raise ForbiddenError("This address does not belong to you.")
        if payload.scheduled_start_at <= datetime.now(UTC):
            raise ValidationAppError("scheduled_start_at must be in the future.")
        if payload.booking_type == BookingType.CARE_PLAN and not payload.total_visits:
            raise ValidationAppError("total_visits is required for a care plan booking.")

        breakdown = await self.quote(service=service, coupon_code=payload.coupon_code)
        address_point = to_shape(address.location)

        booking = Booking(
            booking_code=_generate_booking_code(),
            patient_id=patient_id,
            service_id=service.id,
            address_id=address.id,
            booking_type=payload.booking_type,
            status=BookingStatus.CREATED,
            required_professional_type=service.required_professional_type,
            scheduled_start_at=payload.scheduled_start_at,
            scheduled_end_at=payload.scheduled_start_at
            + timedelta(minutes=service.duration_minutes),
            service_name_snapshot=service.name,
            address_snapshot=(
                f"{address.line1}, {address.line2 or ''}, {address.city} {address.pincode}"
            ).strip(),
            service_location=WKTElement(address_point.wkt, srid=4326),
            base_price=breakdown.base_price,
            discount_amount=breakdown.discount_amount,
            platform_fee=breakdown.platform_fee,
            tax_amount=breakdown.tax_amount,
            total_amount=breakdown.total_amount,
            professional_payout_amount=breakdown.professional_payout_amount,
            commission_pct=breakdown.commission_pct,
            patient_notes=payload.patient_notes,
        )
        self.bookings.add(booking)
        await self.session.flush()
        return booking

    async def get_owned_booking(self, booking_id: uuid.UUID, *, patient_id: uuid.UUID) -> Booking:
        booking = await self.bookings.get(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        if booking.patient_id != patient_id:
            raise ForbiddenError("This booking does not belong to you.")
        return booking

    async def cancel(self, booking: Booking, *, cancelled_by_id: uuid.UUID, reason: str) -> Booking:
        if booking.status in (
            BookingStatus.COMPLETED,
            BookingStatus.CANCELLED,
            BookingStatus.NO_SHOW,
        ):
            raise ValidationAppError(f"A {booking.status} booking cannot be cancelled.")

        minutes_to_start = (
            booking.scheduled_start_at.replace(tzinfo=UTC) - datetime.now(UTC)
        ).total_seconds() / 60
        fee = 0.0
        if minutes_to_start < settings.FREE_CANCELLATION_WINDOW_MINUTES and booking.status in (
            BookingStatus.ASSIGNED,
            BookingStatus.CONFIRMED,
        ):
            fee = round(float(booking.total_amount) * settings.CANCELLATION_FEE_PCT / 100, 2)

        booking.cancellation_reason = reason
        booking.cancelled_by_id = cancelled_by_id
        booking.cancelled_at = datetime.now(UTC)
        booking.cancellation_fee_amount = fee
        await self.transition_status(
            booking, BookingStatus.CANCELLED, reason=reason, changed_by_id=cancelled_by_id
        )
        return booking
