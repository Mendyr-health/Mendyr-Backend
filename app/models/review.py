"""Post-visit ratings — patient rates professional (and optionally vice versa)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, UUIDPKMixin


class Review(Base, UUIDPKMixin):
    __tablename__ = "reviews"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reviewee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(50)), nullable=True
    )  # e.g. ["punctual", "gentle", "knowledgeable"]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("booking_id", "reviewer_id", name="uq_review_booking_reviewer"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="rating_range"),
    )
