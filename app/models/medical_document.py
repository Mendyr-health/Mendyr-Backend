"""A patient's own medical files — prescriptions, lab reports, referrals. Optionally attached
to a booking, in which case the assigned professional can view it while the visit is live."""

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPKMixin

# Plain strings, not a Postgres enum: adding a kind later needs no migration.
MEDICAL_DOCUMENT_TYPES = ("prescription", "lab_report", "referral", "other")


class MedicalDocument(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "medical_documents"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True
    )
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # Object key in the private bucket (`medical/<user_id>/<uuid>.<ext>`), never a URL.
    file_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_medical_documents_user_id", "user_id"),
        Index("ix_medical_documents_booking_id", "booking_id"),
    )
