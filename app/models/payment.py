"""Patient payments (Razorpay) and professional payouts."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import PaymentMethod, PaymentStatus, PayoutStatus
from app.db.base_class import Base, TimestampMixin, UUIDPKMixin
from app.db.types import pg_enum


class Payment(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "payments"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    provider: Mapped[str] = mapped_column(String(30), default="razorpay", nullable=False)
    provider_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    provider_signature: Mapped[str | None] = mapped_column(String(255), nullable=True)

    method: Mapped[PaymentMethod | None] = mapped_column(
        pg_enum(PaymentMethod, "payment_method"), nullable=True
    )
    status: Mapped[PaymentStatus] = mapped_column(
        pg_enum(PaymentStatus, "payment_status"), default=PaymentStatus.PENDING, nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    amount_refunded: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)

    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_webhook_payload: Mapped[str | None] = mapped_column(Text, nullable=True)


class Payout(Base, UUIDPKMixin, TimestampMixin):
    """Aggregated payout of a professional's earnings for a settlement cycle (e.g. weekly)."""

    __tablename__ = "payouts"

    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professional_profiles.id"), nullable=False, index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_visits: Mapped[int] = mapped_column(nullable=False)
    gross_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    commission_deducted: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    adjustments: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    net_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    status: Mapped[PayoutStatus] = mapped_column(
        pg_enum(PayoutStatus, "payout_status"), default=PayoutStatus.PENDING, nullable=False
    )
    provider_reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
