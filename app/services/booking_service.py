"""Booking lifecycle: quoting, creation, accept/release, cancellation, and the patient's and
professional's views of a booking.

Matching is an open-request model, not timed offers: a new booking is published straight
away as `SEARCHING`, every professional it suits sees it in their requests list (see
`BookingRepository.open_requests_query` for the rules), and the first to accept gets it
(`ASSIGNED`). They then start (`IN_PROGRESS`, see `VisitService`) and complete the visit.
No background worker is involved, so this runs as-is on FastAPI Cloud.

Payment is collected after the visit, outside the app, for the prototype — nothing waits
on a payment step. The Razorpay endpoints still exist for when online payment comes back.
"""

import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import BookingStatus, BookingType, VerificationStatus
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.models.address import Address
from app.models.booking import Booking, BookingStatusHistory
from app.models.professional import ProfessionalProfile
from app.models.service import Service
from app.repositories.booking_repo import (
    BookingRepository,
    OpenRequestRow,
    PatientBookingRow,
    ProfessionalBookingRow,
)
from app.schemas.booking import (
    AssignedProfessionalRead,
    BookingCreateIn,
    BookingRead,
    BookingRequestRead,
    ProfessionalBookingRead,
)
from app.services.notification_service import NotificationService
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
        BookingStatus.EN_ROUTE,
        BookingStatus.IN_PROGRESS,
        BookingStatus.SEARCHING,  # professional released it
        BookingStatus.CANCELLED,
    },
    BookingStatus.CONFIRMED: {
        BookingStatus.EN_ROUTE,
        BookingStatus.IN_PROGRESS,
        BookingStatus.SEARCHING,
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
    BookingStatus.FAILED: {BookingStatus.SEARCHING, BookingStatus.CANCELLED},
}

# A patient can cancel until the visit has actually started.
CANCELLABLE_STATUSES = frozenset(
    {
        BookingStatus.CREATED,
        BookingStatus.SEARCHING,
        BookingStatus.ASSIGNED,
        BookingStatus.CONFIRMED,
        BookingStatus.EN_ROUTE,
        BookingStatus.FAILED,
    }
)
# A professional can hand a booking back until they've set off for it.
RELEASABLE_STATUSES = frozenset({BookingStatus.ASSIGNED, BookingStatus.CONFIRMED})

CODE_ALPHABET = string.ascii_uppercase + string.digits


def _generate_booking_code() -> str:
    return "MNDYR-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))


def _format_address(address: Address) -> str:
    parts = [address.line1, address.line2, address.landmark, f"{address.city} {address.pincode}"]
    return ", ".join(part.strip() for part in parts if part and part.strip())


def ensure_can_take_requests(professional: ProfessionalProfile) -> None:
    if professional.verification_status != VerificationStatus.APPROVED:
        raise ForbiddenError("Your profile is still being verified.")
    if not professional.is_accepting_bookings:
        raise ValidationAppError("Turn on 'Accepting requests' to take new bookings.")
    if professional.current_location is None:
        raise ValidationAppError("Set your service area to see requests near you.")


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.bookings = BookingRepository(session)
        self.pricing = PricingService(session)
        self.notifications = NotificationService(session)

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
        now = datetime.now(UTC)
        if payload.scheduled_start_at <= now:
            raise ValidationAppError("Please pick a time in the future.")
        if payload.scheduled_start_at > now + timedelta(days=settings.BOOKING_MAX_DAYS_AHEAD):
            raise ValidationAppError(
                f"Visits can be booked up to {settings.BOOKING_MAX_DAYS_AHEAD} days ahead."
            )
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
            # Published straight away — see the module docstring.
            status=BookingStatus.SEARCHING,
            required_professional_type=service.required_professional_type,
            scheduled_start_at=payload.scheduled_start_at,
            scheduled_end_at=payload.scheduled_start_at
            + timedelta(minutes=service.duration_minutes),
            service_name_snapshot=service.name,
            address_snapshot=_format_address(address),
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
        self.session.add(
            BookingStatusHistory(
                booking_id=booking.id,
                from_status=None,
                to_status=BookingStatus.SEARCHING,
                changed_by_id=patient_id,
                reason="Booking requested",
                created_at=now,
            )
        )
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
        if booking.status not in CANCELLABLE_STATUSES:
            if booking.status == BookingStatus.IN_PROGRESS:
                raise ValidationAppError("This visit has already started and can't be cancelled.")
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

    # ── Professional side ───────────────────────────────────────────────

    async def list_open_requests(self, professional: ProfessionalProfile) -> list[OpenRequestRow]:
        if (
            professional.verification_status != VerificationStatus.APPROVED
            or not professional.is_accepting_bookings
            or professional.current_location is None
        ):
            return []
        return await self.bookings.list_open_requests(professional, now=datetime.now(UTC))

    async def accept(self, booking_id: uuid.UUID, professional: ProfessionalProfile) -> Booking:
        """First accept wins. The row lock makes a concurrent second accept wait, then see
        the booking already ASSIGNED and get a 409 rather than double-booking it."""
        ensure_can_take_requests(professional)
        booking = await self.bookings.get_for_update(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        if booking.status != BookingStatus.SEARCHING:
            raise ConflictError("Another professional has already accepted this request.")
        if not await self.bookings.is_open_request_for(
            booking_id, professional, now=datetime.now(UTC)
        ):
            raise ForbiddenError("This request is outside your services, area or timings.")

        booking.professional_id = professional.id
        await self.transition_status(
            booking,
            BookingStatus.ASSIGNED,
            reason="Accepted by professional",
            changed_by_id=professional.user_id,
        )
        await self.notifications.notify_offer_accepted(booking)
        return booking

    async def release(self, booking_id: uuid.UUID, professional: ProfessionalProfile) -> Booking:
        """The assigned professional can't make it: put the request back on the board."""
        booking = await self.bookings.get_for_update(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        if booking.professional_id != professional.id:
            raise ForbiddenError("This booking is not assigned to you.")
        if booking.status not in RELEASABLE_STATUSES:
            raise ValidationAppError("Only a visit that hasn't started can be handed back.")

        booking.professional_id = None
        await self.transition_status(
            booking,
            BookingStatus.SEARCHING,
            reason="Released by professional",
            changed_by_id=professional.user_id,
        )
        await self.notifications.notify_booking_status(
            booking,
            title="Finding you another professional",
            body=f"Your {booking.service_name_snapshot} professional can no longer make it — "
            "we've reopened your request.",
        )
        return booking

    # ── Views ───────────────────────────────────────────────────────────

    async def patient_view(self, booking_id: uuid.UUID) -> BookingRead:
        row = await self.bookings.get_patient_row(booking_id)
        if row is None:
            raise NotFoundError("Booking not found.")
        review_rating = await self.bookings.get_review_rating(booking_id)
        return to_patient_read(row, review_rating=review_rating)

    async def professional_view(
        self, booking_id: uuid.UUID, professional: ProfessionalProfile
    ) -> ProfessionalBookingRead:
        row = await self.bookings.get_professional_row(booking_id, professional.id)
        if row is None:
            raise NotFoundError("Booking not found.")
        return to_professional_read(row)


def to_patient_read(row: PatientBookingRow, *, review_rating: int | None) -> BookingRead:
    booking, professional, professional_user, visit = row
    assigned = None
    if professional is not None and professional_user is not None:
        assigned = AssignedProfessionalRead(
            id=professional.id,
            full_name=professional_user.full_name,
            avatar_url=professional_user.avatar_url,
            phone_number=professional_user.phone_number,
            professional_type=professional.professional_type,
            years_of_experience=professional.years_of_experience,
            average_rating=float(professional.average_rating),
            total_ratings=professional.total_ratings,
            languages_spoken=professional.languages_spoken,
        )
    read = BookingRead.model_validate(booking)
    read.professional = assigned
    read.visit_summary_notes = visit.visit_summary_notes if visit else None
    read.review_rating = review_rating
    return read


def to_professional_read(row: ProfessionalBookingRow) -> ProfessionalBookingRead:
    booking, patient, address, visit = row
    point = to_shape(booking.service_location)
    return ProfessionalBookingRead(
        id=booking.id,
        booking_code=booking.booking_code,
        status=booking.status,
        service_name=booking.service_name_snapshot,
        scheduled_start_at=booking.scheduled_start_at,
        scheduled_end_at=booking.scheduled_end_at,
        address=booking.address_snapshot,
        landmark=address.landmark if address else None,
        instructions=address.instructions_for_professional if address else None,
        latitude=point.y,
        longitude=point.x,
        # The address's on-site contact (e.g. a parent being cared for) when one was given.
        patient_name=(address.contact_name if address and address.contact_name else None)
        or patient.full_name,
        patient_phone=(address.contact_phone if address and address.contact_phone else None)
        or patient.phone_number,
        patient_notes=booking.patient_notes,
        earning_amount=float(booking.professional_payout_amount),
        started_at=visit.checked_in_at if visit else None,
        completed_at=visit.checked_out_at if visit else None,
        visit_summary_notes=visit.visit_summary_notes if visit else None,
        created_at=booking.created_at,
    )


def to_request_read(row: OpenRequestRow) -> BookingRequestRead:
    booking, address, distance_meters = row
    area = f"{address.city} {address.pincode}" if address else "Area unavailable"
    if address and address.line2:
        area = f"{address.line2}, {area}"
    return BookingRequestRead(
        id=booking.id,
        booking_code=booking.booking_code,
        service_id=booking.service_id,
        service_name=booking.service_name_snapshot,
        scheduled_start_at=booking.scheduled_start_at,
        scheduled_end_at=booking.scheduled_end_at,
        area=area,
        distance_km=round(distance_meters / 1000, 1),
        earning_amount=float(booking.professional_payout_amount),
        patient_notes=booking.patient_notes,
        created_at=booking.created_at,
    )
