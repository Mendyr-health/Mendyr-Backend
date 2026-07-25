"""Booking lifecycle: care plans, bookings, dispatch offers, status history and check-in/out."""

import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    BookingStatus,
    BookingType,
    OfferStatus,
    ProfessionalType,
    VisitEvent,
)
from app.db.base_class import Base, TimestampMixin, UUIDPKMixin
from app.db.types import pg_enum


class CarePlan(Base, UUIDPKMixin, TimestampMixin):
    """A multi-day recurring package (e.g. '7-day post-surgery nursing care, twice daily').

    A CarePlan owns N child Bookings — one per scheduled visit — created up front so the
    patient sees the full schedule, but dispatched to a professional individually per visit.
    """

    __tablename__ = "care_plans"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id"), nullable=False
    )
    address_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("addresses.id"), nullable=False
    )

    total_visits: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    visits_per_day: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    preferred_professional_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professional_profiles.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="care_plan")


class Booking(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "bookings"

    booking_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False
    )  # e.g. MNDYR-8F3K2

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    professional_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professional_profiles.id"), nullable=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id"), nullable=False
    )
    address_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("addresses.id"), nullable=False
    )
    care_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("care_plans.id"), nullable=True
    )

    booking_type: Mapped[BookingType] = mapped_column(
        pg_enum(BookingType, "booking_type"), default=BookingType.ONE_TIME, nullable=False
    )
    status: Mapped[BookingStatus] = mapped_column(
        pg_enum(BookingStatus, "booking_status"),
        default=BookingStatus.CREATED,
        nullable=False,
    )
    required_professional_type: Mapped[ProfessionalType] = mapped_column(
        pg_enum(ProfessionalType, "professional_type"), nullable=False
    )

    scheduled_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Immutable snapshot of catalogue + address at booking time — never recompute from live rows,
    # since the catalogue price / patient's saved address can change after the booking is placed.
    service_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    address_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    service_location: Mapped[str] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )

    base_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    platform_fee: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    professional_payout_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    commission_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    coupon_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coupons.id"), nullable=True
    )

    patient_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_fee_amount: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0, nullable=False
    )

    care_plan: Mapped["CarePlan | None"] = relationship(back_populates="bookings")
    offers: Mapped[list["BookingOffer"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )
    status_history: Mapped[list["BookingStatusHistory"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )
    visit: Mapped["BookingVisit | None"] = relationship(
        back_populates="booking", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_bookings_patient_status", "patient_id", "status"),
        Index("ix_bookings_professional_status", "professional_id", "status"),
        Index("ix_bookings_scheduled_start", "scheduled_start_at"),
    )


class BookingStatusHistory(Base, UUIDPKMixin):
    """Append-only audit trail of every state transition — never mutated, only inserted."""

    __tablename__ = "booking_status_history"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[BookingStatus | None] = mapped_column(
        pg_enum(BookingStatus, "booking_status"), nullable=True
    )
    to_status: Mapped[BookingStatus] = mapped_column(
        pg_enum(BookingStatus, "booking_status"), nullable=False
    )
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    booking: Mapped["Booking"] = relationship(back_populates="status_history")


class BookingOffer(Base, UUIDPKMixin, TimestampMixin):
    """One dispatch round to one candidate professional. The matching engine creates a batch
    of these per round, first ACCEPT wins, the rest are auto-CANCELLED."""

    __tablename__ = "booking_offers"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professional_profiles.id"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    distance_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[OfferStatus] = mapped_column(
        pg_enum(OfferStatus, "offer_status"), default=OfferStatus.PENDING, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    booking: Mapped["Booking"] = relationship(back_populates="offers")

    __table_args__ = (
        Index("ix_offers_professional_status", "professional_id", "status"),
        Index("ix_offers_booking_round", "booking_id", "round_number"),
    )


class BookingVisit(Base, UUIDPKMixin, TimestampMixin):
    """Ground-truth of what actually happened at the patient's home: geofenced check-in/out."""

    __tablename__ = "booking_visits"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    en_route_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_in_location: Mapped[str | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=True
    )
    checked_in_distance_meters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_out_location: Mapped[str | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=True
    )
    visit_summary_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # professional's clinical notes
    vitals_recorded: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # free-form JSON string (BP, SpO2, etc.)
    proof_of_visit_photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    booking: Mapped["Booking"] = relationship(back_populates="visit")


class VisitTrackingPing(Base, UUIDPKMixin):
    """Coarse live-location breadcrumbs while `en_route`, for the patient's live-tracking map.
    High-frequency pings live in Redis; only a sampled trail is persisted here for support/audit."""

    __tablename__ = "visit_tracking_pings"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False
    )
    event: Mapped[VisitEvent] = mapped_column(pg_enum(VisitEvent, "visit_event"), nullable=False)
    location: Mapped[str] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_tracking_booking_time", "booking_id", "recorded_at"),)
