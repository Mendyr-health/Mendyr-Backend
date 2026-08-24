import uuid
from datetime import datetime

from sqlalchemy import func, select

from app.core.constants import BookingStatus, OfferStatus
from app.models.booking import Booking, BookingOffer
from app.repositories.base import BaseRepository


class BookingRepository(BaseRepository[Booking]):
    model = Booking

    async def get_by_code(self, booking_code: str) -> Booking | None:
        result = await self.session.execute(
            select(Booking).where(Booking.booking_code == booking_code)
        )
        return result.scalar_one_or_none()

    async def list_for_patient(
        self, patient_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[Booking]:
        result = await self.session.execute(
            select(Booking)
            .where(Booking.patient_id == patient_id)
            .order_by(Booking.scheduled_start_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_for_patient(self, patient_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Booking).where(Booking.patient_id == patient_id)
        )
        return result.scalar_one()

    async def list_for_professional(
        self, professional_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[Booking]:
        result = await self.session.execute(
            select(Booking)
            .where(Booking.professional_id == professional_id)
            .order_by(Booking.scheduled_start_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_for_professional(self, professional_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Booking)
            .where(Booking.professional_id == professional_id)
        )
        return result.scalar_one()

    async def list_completed_for_professional_between(
        self, professional_id: uuid.UUID, *, start: datetime, end: datetime
    ) -> list[Booking]:
        """Completed visits in [start, end) — the base dataset for earnings aggregation."""
        result = await self.session.execute(
            select(Booking).where(
                Booking.professional_id == professional_id,
                Booking.status == BookingStatus.COMPLETED,
                Booking.scheduled_start_at >= start,
                Booking.scheduled_start_at < end,
            )
        )
        return list(result.scalars().all())


class BookingOfferRepository(BaseRepository[BookingOffer]):
    model = BookingOffer

    async def get_pending_for_professional(
        self, booking_id: uuid.UUID, professional_id: uuid.UUID
    ) -> BookingOffer | None:
        result = await self.session.execute(
            select(BookingOffer).where(
                BookingOffer.booking_id == booking_id,
                BookingOffer.professional_id == professional_id,
                BookingOffer.status == OfferStatus.PENDING,
            )
        )
        return result.scalar_one_or_none()

    async def list_pending_for_booking(self, booking_id: uuid.UUID) -> list[BookingOffer]:
        result = await self.session.execute(
            select(BookingOffer).where(
                BookingOffer.booking_id == booking_id, BookingOffer.status == OfferStatus.PENDING
            )
        )
        return list(result.scalars().all())

    async def latest_round_number(self, booking_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(BookingOffer.round_number)
            .where(BookingOffer.booking_id == booking_id)
            .order_by(BookingOffer.round_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none() or 0
