"""Post-visit ratings — updates the professional's rolling average on every new review."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import BookingStatus
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.models.review import Review
from app.repositories.booking_repo import BookingRepository
from app.repositories.professional_repo import ProfessionalRepository
from app.schemas.review import ReviewCreateIn


class ReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.bookings = BookingRepository(session)
        self.professionals = ProfessionalRepository(session)

    async def create_review(self, *, reviewer_id: uuid.UUID, payload: ReviewCreateIn) -> Review:
        booking = await self.bookings.get(payload.booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        if booking.patient_id != reviewer_id:
            raise ForbiddenError("You can only review your own bookings.")
        if booking.status != BookingStatus.COMPLETED:
            raise ValidationAppError("You can only review a completed booking.")
        if booking.professional_id is None:
            raise ValidationAppError("This booking has no assigned professional to review.")

        professional = await self.professionals.get(booking.professional_id)
        if professional is None:
            raise NotFoundError("Professional not found.")

        review = Review(
            booking_id=booking.id,
            reviewer_id=reviewer_id,
            reviewee_id=professional.user_id,
            rating=payload.rating,
            comment=payload.comment,
            tags=payload.tags,
            created_at=datetime.now(UTC),
        )
        self.session.add(review)

        try:
            await self.session.flush()
        except Exception as exc:  # unique constraint -> booking already reviewed
            raise ConflictError("You have already reviewed this booking.") from exc

        total_before = professional.total_ratings
        new_total = total_before + 1
        professional.average_rating = (
            float(professional.average_rating) * total_before + payload.rating
        ) / new_total
        professional.total_ratings = new_total
        await self.session.flush()
        return review
