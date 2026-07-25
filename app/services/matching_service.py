"""Dispatch engine — the heart of the marketplace: finds and offers a booking to nearby
qualified professionals, round by round, until one accepts or candidates are exhausted.

Design (mirrors how Snabbit/Urban Company-style on-demand matching works):
  1. Round 1: offer to the `OFFERS_PER_ROUND` closest ONLINE, APPROVED professionals within
     the default search radius. Each offer has a short TTL (`BOOKING_OFFER_TTL_SECONDS`).
  2. First to ACCEPT wins — all sibling offers in that round are cancelled, booking -> ASSIGNED.
  3. If a round fully expires with no acceptance, `expire_and_escalate` widens the radius and
     starts the next round (up to `BOOKING_MAX_OFFER_ROUNDS`).
  4. After the last round, the booking fails with `NoProfessionalAvailableError` and support/ops
     is notified to intervene manually.

Round expiry is driven by a Celery beat task (see `app.workers.tasks.matching`) rather than
inline sleeps, since offers must expire even if no one is actively polling this booking.
"""

import uuid
from datetime import UTC, datetime, timedelta

from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import BookingStatus, OfferStatus
from app.core.exceptions import NoProfessionalAvailableError, NotFoundError, ValidationAppError
from app.models.booking import Booking, BookingOffer
from app.repositories.booking_repo import BookingOfferRepository, BookingRepository
from app.repositories.professional_repo import ProfessionalRepository
from app.services.booking_service import BookingService
from app.services.notification_service import NotificationService

OFFERS_PER_ROUND = 3


class MatchingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.bookings = BookingRepository(session)
        self.offers = BookingOfferRepository(session)
        self.professionals = ProfessionalRepository(session)
        self.booking_service = BookingService(session)
        self.notifications = NotificationService(session)

    def _radius_for_round(self, round_number: int) -> float:
        """Widen the search radius each round so later rounds cast a bigger net."""
        step = (settings.MAX_SEARCH_RADIUS_KM - settings.DEFAULT_SEARCH_RADIUS_KM) / max(
            settings.BOOKING_MAX_OFFER_ROUNDS - 1, 1
        )
        km = settings.DEFAULT_SEARCH_RADIUS_KM + step * (round_number - 1)
        return min(km, settings.MAX_SEARCH_RADIUS_KM) * 1000  # metres

    async def start_dispatch(self, booking_id: uuid.UUID) -> None:
        booking = await self.bookings.get(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        await self._run_round(booking, round_number=1)

    async def _run_round(self, booking: Booking, *, round_number: int) -> None:
        already_offered = {
            o.professional_id for o in (await self.offers.list_pending_for_booking(booking.id))
        }
        location_wkt = to_shape(booking.service_location).wkt

        candidates = await self.professionals.find_nearby_candidates(
            service_id=booking.service_id,
            professional_type=booking.required_professional_type,
            location_wkt=location_wkt,
            radius_meters=self._radius_for_round(round_number),
            exclude_ids=already_offered,
            limit=OFFERS_PER_ROUND,
        )

        if not candidates:
            if round_number < settings.BOOKING_MAX_OFFER_ROUNDS:
                await self._run_round(booking, round_number=round_number + 1)
                return
            await self.booking_service.transition_status(
                booking,
                BookingStatus.FAILED,
                reason="No professionals available after all offer rounds.",
            )
            raise NoProfessionalAvailableError(
                "No professionals are currently available for this service."
            )

        expires_at = datetime.now(UTC) + timedelta(seconds=settings.BOOKING_OFFER_TTL_SECONDS)
        for professional, distance_meters in candidates:
            offer = BookingOffer(
                booking_id=booking.id,
                professional_id=professional.id,
                round_number=round_number,
                distance_meters=int(distance_meters),
                status=OfferStatus.PENDING,
                expires_at=expires_at,
            )
            self.offers.add(offer)
            await self.notifications.notify_new_offer(
                professional_id=professional.id, booking=booking
            )

        if booking.status != BookingStatus.SEARCHING:
            await self.booking_service.transition_status(booking, BookingStatus.SEARCHING)
        await self.session.flush()

    async def respond_to_offer(
        self, *, booking_id: uuid.UUID, professional_id: uuid.UUID, accept: bool
    ) -> Booking:
        offer = await self.offers.get_pending_for_professional(booking_id, professional_id)
        if offer is None:
            raise NotFoundError("No pending offer found for this booking.")
        if offer.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            offer.status = OfferStatus.EXPIRED
            await self.session.flush()
            raise ValidationAppError("This offer has expired.")

        booking = await self.bookings.get(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")

        if not accept:
            offer.status = OfferStatus.REJECTED
            offer.responded_at = datetime.now(UTC)
            await self.session.flush()
            return booking

        offer.status = OfferStatus.ACCEPTED
        offer.responded_at = datetime.now(UTC)

        for sibling in await self.offers.list_pending_for_booking(booking_id):
            sibling.status = OfferStatus.CANCELLED
            sibling.responded_at = datetime.now(UTC)

        booking.professional_id = professional_id
        await self.booking_service.transition_status(booking, BookingStatus.ASSIGNED)
        await self.notifications.notify_offer_accepted(booking)
        return booking

    async def expire_and_escalate(self, booking_id: uuid.UUID) -> None:
        """Called by the Celery beat sweep for offers whose TTL has lapsed with no response."""
        booking = await self.bookings.get(booking_id)
        if booking is None or booking.status != BookingStatus.SEARCHING:
            return

        pending = await self.offers.list_pending_for_booking(booking_id)
        now = datetime.now(UTC)
        expired = [o for o in pending if o.expires_at.replace(tzinfo=UTC) < now]
        if not expired or len(expired) != len(pending):
            return  # round still has live offers outstanding

        for offer in expired:
            offer.status = OfferStatus.EXPIRED
        next_round = (await self.offers.latest_round_number(booking_id)) + 1
        await self._run_round(booking, round_number=next_round)
