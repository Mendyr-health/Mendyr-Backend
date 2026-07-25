"""Patient-specific profile data (medical context relevant to home-care bookings)."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPKMixin


class PatientProfile(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "patient_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Care context — surfaced to the assigned professional before the visit.
    known_conditions: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)), nullable=True)
    allergies: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)), nullable=True)
    current_medications: Mapped[str | None] = mapped_column(Text, nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(15), nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    date_of_birth: Mapped[datetime | None] = mapped_column(nullable=True)

    user: Mapped["User"] = relationship(back_populates="patient_profile")
