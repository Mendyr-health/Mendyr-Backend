"""Healthcare professional profile, KYC documents, specializations, availability, live location."""

import uuid
from datetime import datetime, time

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    AvailabilityStatus,
    DocumentType,
    ProfessionalType,
    VerificationStatus,
)
from app.db.base_class import Base, TimestampMixin, UUIDPKMixin
from app.db.types import pg_enum


class ProfessionalProfile(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "professional_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    professional_type: Mapped[ProfessionalType] = mapped_column(
        pg_enum(ProfessionalType, "professional_type"), nullable=False
    )
    years_of_experience: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    council_registration_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    languages_spoken: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)), nullable=True)

    verification_status: Mapped[VerificationStatus] = mapped_column(
        pg_enum(VerificationStatus, "verification_status"),
        default=VerificationStatus.PENDING,
        nullable=False,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    availability_status: Mapped[AvailabilityStatus] = mapped_column(
        pg_enum(AvailabilityStatus, "availability_status"),
        default=AvailabilityStatus.OFFLINE,
        nullable=False,
    )
    # Live location, updated frequently while ONLINE/ON_VISIT — powers nearest-professional search.
    current_location: Mapped[str | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=True
    )
    location_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    base_service_radius_km: Mapped[float] = mapped_column(Numeric(5, 2), default=12, nullable=False)
    average_rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0, nullable=False)
    total_ratings: Mapped[int] = mapped_column(default=0, nullable=False)
    total_visits_completed: Mapped[int] = mapped_column(default=0, nullable=False)

    bank_account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(String(15), nullable=True)
    bank_account_holder_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    upi_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    is_accepting_bookings: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="professional_profile")
    documents: Mapped[list["ProfessionalDocument"]] = relationship(
        back_populates="professional", cascade="all, delete-orphan"
    )
    specializations: Mapped[list["ProfessionalSpecialization"]] = relationship(
        back_populates="professional", cascade="all, delete-orphan"
    )
    availability_slots: Mapped[list["ProfessionalAvailabilitySlot"]] = relationship(
        back_populates="professional", cascade="all, delete-orphan"
    )
    services: Mapped[list["ProfessionalService"]] = relationship(
        back_populates="professional", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_professional_type_status", "professional_type", "verification_status"),
        Index(
            "ix_professional_current_location",
            "current_location",
            postgresql_using="gist",
        ),
    )


class ProfessionalDocument(Base, UUIDPKMixin, TimestampMixin):
    """KYC uploads reviewed by ops before a professional is APPROVED to receive bookings."""

    __tablename__ = "professional_documents"

    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("professional_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_type: Mapped[DocumentType] = mapped_column(
        pg_enum(DocumentType, "document_type"), nullable=False
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        pg_enum(VerificationStatus, "verification_status"),
        default=VerificationStatus.PENDING,
        nullable=False,
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    professional: Mapped["ProfessionalProfile"] = relationship(back_populates="documents")


class Specialization(Base, UUIDPKMixin, TimestampMixin):
    """Lookup table: e.g. ICU Care, Wound Dressing, Post-Operative Care, Elder Care, Baby Care."""

    __tablename__ = "specializations"

    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProfessionalSpecialization(Base, UUIDPKMixin):
    __tablename__ = "professional_specializations"

    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("professional_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    specialization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("specializations.id", ondelete="CASCADE"), nullable=False
    )
    years_of_experience: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)

    professional: Mapped["ProfessionalProfile"] = relationship(back_populates="specializations")
    specialization: Mapped["Specialization"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "professional_id", "specialization_id", name="uq_professional_specialization"
        ),
    )


class ProfessionalAvailabilitySlot(Base, UUIDPKMixin):
    """Recurring weekly working hours, used to filter candidates before geo-distance ranking."""

    __tablename__ = "professional_availability_slots"

    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("professional_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0=Monday ... 6=Sunday
    start_time: Mapped[time] = mapped_column(nullable=False)
    end_time: Mapped[time] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    professional: Mapped["ProfessionalProfile"] = relationship(back_populates="availability_slots")

    __table_args__ = (Index("ix_availability_professional_day", "professional_id", "day_of_week"),)
