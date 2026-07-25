"""Patient wallet ledger and promotional coupons."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import CouponDiscountType, WalletTxnReason, WalletTxnType
from app.db.base_class import Base, TimestampMixin, UUIDPKMixin
from app.db.types import pg_enum


class Wallet(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "wallets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    balance: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)

    transactions: Mapped[list["WalletTransaction"]] = relationship(
        back_populates="wallet", cascade="all, delete-orphan"
    )


class WalletTransaction(Base, UUIDPKMixin):
    """Immutable ledger entry. `balance_after` is a running-total snapshot for fast history reads;
    the true source of truth is the sum of all entries — reconcile against it periodically."""

    __tablename__ = "wallet_transactions"

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False
    )
    txn_type: Mapped[WalletTxnType] = mapped_column(
        pg_enum(WalletTxnType, "wallet_txn_type"), nullable=False
    )
    reason: Mapped[WalletTxnReason] = mapped_column(
        pg_enum(WalletTxnReason, "wallet_txn_reason"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    reference_booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    wallet: Mapped["Wallet"] = relationship(back_populates="transactions")


class Coupon(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "coupons"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discount_type: Mapped[CouponDiscountType] = mapped_column(
        pg_enum(CouponDiscountType, "coupon_discount_type"), nullable=False
    )
    discount_value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    max_discount_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    min_order_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    max_redemptions_total: Mapped[int | None] = mapped_column(nullable=True)
    max_redemptions_per_user: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CouponRedemption(Base, UUIDPKMixin):
    __tablename__ = "coupon_redemptions"

    coupon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False
    )
    discount_applied: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("coupon_id", "booking_id", name="uq_coupon_booking"),)
