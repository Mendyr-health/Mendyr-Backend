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
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config_registry import BookingRules, FeatureFlags, PrivacyConfig
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
from app.models.user import User
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
    StatusEvent,
)
from app.services.config_service import ConfigService
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

# Statuses in which the patient needs the visit PIN to hand to the professional.
PIN_VISIBLE_STATUSES = frozenset(
    {BookingStatus.ASSIGNED, BookingStatus.CONFIRMED, BookingStatus.EN_ROUTE}
)
# Fee applies once a professional is committed to the visit.
FEE_STATUSES = frozenset({BookingStatus.ASSIGNED, BookingStatus.CONFIRMED, BookingStatus.EN_ROUTE})
# Slack on the minimum lead time: the app computes "now" a little before the request lands.
LEAD_TIME_GRACE = timedelta(minutes=5)
STALE_SWEEP_INTERVAL_SECONDS = 60
_last_stale_sweep = 0.0

CancelledBy = Literal["patient", "professional", "admin", "system"]


def user_ref(user_id: uuid.UUID) -> str:
    """Short, stable reference shown instead of a name/number once contact is hidden."""
    return "MU-" + user_id.hex[:6].upper()


def is_contact_hidden(
    booking: Booking, privacy: PrivacyConfig, *, completed_at: datetime | None
) -> bool:
    if booking.status in privacy.hide_contact_on_statuses:
        return True
    if booking.status == BookingStatus.COMPLETED and privacy.hide_contact_hours_after_completion:
        done = (completed_at or booking.updated_at).replace(tzinfo=UTC)
        hidden_after = timedelta(hours=privacy.hide_contact_hours_after_completion)
        return datetime.now(UTC) - done > hidden_after
    return False


def cancelled_by(booking: Booking, *, professional_user_id: uuid.UUID | None) -> CancelledBy | None:
    if booking.status == BookingStatus.FAILED:
        return "system"
    if booking.status != BookingStatus.CANCELLED:
        return None
    if booking.cancelled_by_id is None:
        return "system"
    if booking.cancelled_by_id == booking.patient_id:
        return "patient"
    if professional_user_id is not None and booking.cancelled_by_id == professional_user_id:
        return "professional"
    return "admin"


def _attr(booking: Booking, key: str) -> str | None:
    return (booking.extended_attributes or {}).get(key)


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
        self.config = ConfigService(session)

    async def _rules(self) -> BookingRules:
        return await self.config.typed("booking.rules", BookingRules)

    async def _features(self) -> FeatureFlags:
        return await self.config.typed("app.features", FeatureFlags)

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
        rules = await self._rules()
        features = await self._features()
        if payload.scheduled_start_at <= now:
            raise ValidationAppError("Please pick a time in the future.")
        earliest = now + timedelta(minutes=rules.min_lead_minutes) - LEAD_TIME_GRACE
        if payload.scheduled_start_at < earliest:
            raise ValidationAppError(
                f"Please pick a slot at least {rules.min_lead_minutes} minutes from now."
            )
        if payload.scheduled_start_at > now + timedelta(days=rules.horizon_days):
            raise ValidationAppError(f"Visits can be booked up to {rules.horizon_days} days ahead.")
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
            extended_attributes={
                # Always generated, only enforced while the `visit_otp` flag is on — turning
                # the flag on then covers bookings made before it.
                "visit_pin": f"{secrets.randbelow(10_000):04d}",
                "preferred_gender": payload.preferred_gender
                if features.gender_preference
                else None,
            },
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

        rules = await self._rules()
        minutes_to_start = (
            booking.scheduled_start_at.replace(tzinfo=UTC) - datetime.now(UTC)
        ).total_seconds() / 60
        fee = 0.0
        if minutes_to_start < rules.free_cancel_window_minutes and booking.status in FEE_STATUSES:
            fee = round(float(booking.total_amount) * rules.cancellation_fee_pct / 100, 2)

        booking.cancellation_reason = reason
        booking.cancelled_by_id = cancelled_by_id
        booking.cancelled_at = datetime.now(UTC)
        booking.cancellation_fee_amount = fee
        await self.transition_status(
            booking, BookingStatus.CANCELLED, reason=reason, changed_by_id=cancelled_by_id
        )
        return booking

    # ── Professional side ───────────────────────────────────────────────

    async def expire_stale_requests(self) -> int:
        """Fail requests nobody accepted before their start time, and tell the patient.

        There's no background worker on FastAPI Cloud, so this runs lazily from the list
        endpoints, at most once a minute per process."""
        global _last_stale_sweep
        if time.monotonic() - _last_stale_sweep < STALE_SWEEP_INTERVAL_SECONDS:
            return 0
        _last_stale_sweep = time.monotonic()
        stale = await self.bookings.list_stale_searching(now=datetime.now(UTC))
        for booking in stale:
            await self.transition_status(
                booking,
                BookingStatus.FAILED,
                reason="No professional was available in time",
            )
            await self.notifications.notify_booking_status(
                booking,
                title="We couldn't find a professional",
                body=f"No one was free for your {booking.service_name_snapshot} visit. "
                "Please try another time — you haven't been charged.",
            )
        return len(stale)

    async def _matching_args(self, professional: ProfessionalProfile) -> dict:
        user = await self.session.get(User, professional.user_id)
        rules = await self._rules()
        return {
            "now": datetime.now(UTC),
            "gender": user.gender if user else None,
            "travel_buffer": timedelta(minutes=rules.travel_buffer_minutes),
        }

    async def list_open_requests(self, professional: ProfessionalProfile) -> list[OpenRequestRow]:
        await self.expire_stale_requests()
        if (
            professional.verification_status != VerificationStatus.APPROVED
            or not professional.is_accepting_bookings
            or professional.current_location is None
        ):
            return []
        return await self.bookings.list_open_requests(
            professional, **await self._matching_args(professional)
        )

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
            booking_id, professional, **await self._matching_args(professional)
        ):
            raise ForbiddenError(
                "This request is outside your services, area or timings, or clashes with a "
                "visit you've already accepted."
            )

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
        history = await self.bookings.list_status_history(booking_id)
        return to_patient_read(
            row,
            review_rating=review_rating,
            history=history,
            privacy=await self.config.typed("privacy", PrivacyConfig),
            features=await self._features(),
        )

    async def professional_reads(
        self, rows: list[ProfessionalBookingRow], professional: ProfessionalProfile
    ) -> list[ProfessionalBookingRead]:
        privacy = await self.config.typed("privacy", PrivacyConfig)
        features = await self._features()
        return [
            to_professional_read(
                row,
                privacy=privacy,
                features=features,
                professional_user_id=professional.user_id,
            )
            for row in rows
        ]

    async def professional_view(
        self, booking_id: uuid.UUID, professional: ProfessionalProfile
    ) -> ProfessionalBookingRead:
        row = await self.bookings.get_professional_row(booking_id, professional.id)
        if row is None:
            raise NotFoundError("Booking not found.")
        return (await self.professional_reads([row], professional))[0]


def to_patient_read(
    row: PatientBookingRow,
    *,
    review_rating: int | None,
    history: list[BookingStatusHistory],
    privacy: PrivacyConfig,
    features: FeatureFlags,
) -> BookingRead:
    booking, professional, professional_user, visit = row
    hidden = is_contact_hidden(
        booking, privacy, completed_at=visit.checked_out_at if visit else None
    )
    assigned = None
    if professional is not None and professional_user is not None:
        assigned = AssignedProfessionalRead(
            id=professional.id,
            full_name=professional_user.full_name,
            avatar_url=professional_user.avatar_url,
            phone_number=None if hidden else professional_user.phone_number,
            user_ref=user_ref(professional_user.id),
            is_verified=professional.verification_status == VerificationStatus.APPROVED,
            gender=professional_user.gender.value,
            professional_type=professional.professional_type,
            years_of_experience=professional.years_of_experience,
            average_rating=float(professional.average_rating),
            total_ratings=professional.total_ratings,
            languages_spoken=professional.languages_spoken,
        )
    read = BookingRead.model_validate(booking)
    read.professional = assigned
    read.cancelled_by = cancelled_by(
        booking, professional_user_id=professional_user.id if professional_user else None
    )
    read.visit_summary_notes = visit.visit_summary_notes if visit else None
    read.vitals_recorded = visit.vitals_recorded if visit else None
    read.en_route_at = visit.en_route_at if visit else None
    read.started_at = visit.checked_in_at if visit else None
    read.completed_at = visit.checked_out_at if visit else None
    read.review_rating = review_rating
    read.preferred_gender = _attr(booking, "preferred_gender")
    read.contact_hidden = hidden
    if features.visit_otp and booking.status in PIN_VISIBLE_STATUSES:
        read.visit_pin = _attr(booking, "visit_pin")
    read.timeline = [
        StatusEvent(status=h.to_status, at=h.created_at, note=h.reason) for h in history
    ]
    return read


def to_professional_read(
    row: ProfessionalBookingRow,
    *,
    privacy: PrivacyConfig,
    features: FeatureFlags,
    professional_user_id: uuid.UUID,
) -> ProfessionalBookingRead:
    booking, patient, address, visit = row
    hidden = is_contact_hidden(
        booking, privacy, completed_at=visit.checked_out_at if visit else None
    )
    point = None if hidden else to_shape(booking.service_location)
    # The address's on-site contact (e.g. a parent being cared for) when one was given.
    contact_name = (address.contact_name if address and address.contact_name else None) or (
        patient.full_name
    )
    contact_phone = (address.contact_phone if address and address.contact_phone else None) or (
        patient.phone_number
    )
    area = f"{address.city} {address.pincode}" if address else "Area unavailable"
    return ProfessionalBookingRead(
        id=booking.id,
        booking_code=booking.booking_code,
        status=booking.status,
        service_name=booking.service_name_snapshot,
        scheduled_start_at=booking.scheduled_start_at,
        scheduled_end_at=booking.scheduled_end_at,
        address=area if hidden else booking.address_snapshot,
        landmark=None if hidden or not address else address.landmark,
        instructions=None if hidden or not address else address.instructions_for_professional,
        latitude=point.y if point else None,
        longitude=point.x if point else None,
        patient_name=contact_name.split()[0] if hidden and contact_name else contact_name,
        patient_phone=None if hidden else contact_phone,
        patient_ref=user_ref(patient.id),
        patient_notes=booking.patient_notes,
        earning_amount=float(booking.professional_payout_amount),
        en_route_at=visit.en_route_at if visit else None,
        started_at=visit.checked_in_at if visit else None,
        completed_at=visit.checked_out_at if visit else None,
        visit_summary_notes=visit.visit_summary_notes if visit else None,
        vitals_recorded=visit.vitals_recorded if visit else None,
        cancellation_reason=booking.cancellation_reason,
        cancelled_by=cancelled_by(booking, professional_user_id=professional_user_id),
        requires_visit_pin=features.visit_otp and bool(_attr(booking, "visit_pin")),
        contact_hidden=hidden,
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
        preferred_gender=_attr(booking, "preferred_gender"),
        created_at=booking.created_at,
    )
