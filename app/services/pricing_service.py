"""Fare calculation — single source of truth for how a booking's price breakdown is derived.

Kept pure/stateless (no DB writes) so it can be unit-tested trivially and reused by both the
pre-booking quote endpoint and the actual booking-creation path, guaranteeing they never drift.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import CouponDiscountType
from app.core.exceptions import ValidationAppError
from app.models.wallet import Coupon


@dataclass(frozen=True)
class PriceBreakdown:
    base_price: float
    discount_amount: float
    platform_fee: float
    tax_amount: float
    total_amount: float
    professional_payout_amount: float
    commission_pct: float


def _round2(value: float) -> float:
    return round(value, 2)


class PricingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _resolve_coupon_discount(self, coupon_code: str | None, base_price: float) -> float:
        if not coupon_code:
            return 0.0

        result = await self.session.execute(
            select(Coupon).where(Coupon.code == coupon_code.upper())
        )
        coupon = result.scalar_one_or_none()
        if coupon is None or not coupon.is_active:
            raise ValidationAppError("Invalid coupon code.")

        now = datetime.now(UTC)
        if not (
            coupon.valid_from.replace(tzinfo=UTC) <= now <= coupon.valid_until.replace(tzinfo=UTC)
        ):
            raise ValidationAppError("This coupon has expired.")
        if base_price < float(coupon.min_order_amount):
            raise ValidationAppError(
                f"Minimum order amount for this coupon is ₹{coupon.min_order_amount}."
            )

        if coupon.discount_type == CouponDiscountType.FLAT:
            discount = float(coupon.discount_value)
        else:
            discount = base_price * float(coupon.discount_value) / 100

        if coupon.max_discount_amount is not None:
            discount = min(discount, float(coupon.max_discount_amount))
        return min(discount, base_price)

    async def quote(self, *, base_price: float, coupon_code: str | None = None) -> PriceBreakdown:
        discount_amount = await self._resolve_coupon_discount(coupon_code, base_price)
        discounted_base = base_price - discount_amount

        commission_pct = settings.PLATFORM_COMMISSION_PCT
        platform_fee = discounted_base * commission_pct / 100
        taxable_amount = (
            discounted_base  # GST is charged on the service value, not the platform fee
        )
        tax_amount = taxable_amount * settings.GST_PCT / 100
        total_amount = discounted_base + tax_amount
        professional_payout_amount = discounted_base - platform_fee

        return PriceBreakdown(
            base_price=_round2(base_price),
            discount_amount=_round2(discount_amount),
            platform_fee=_round2(platform_fee),
            tax_amount=_round2(tax_amount),
            total_amount=_round2(total_amount),
            professional_payout_amount=_round2(professional_payout_amount),
            commission_pct=commission_pct,
        )
