"""Pure-logic tests for fare calculation — no DB needed since coupon_code is omitted."""
import pytest

from app.services.pricing_service import PricingService


@pytest.mark.asyncio
async def test_quote_without_coupon_applies_commission_and_gst(db_session):
    pricing = PricingService(db_session)
    breakdown = await pricing.quote(base_price=1000.0)

    assert breakdown.base_price == 1000.0
    assert breakdown.discount_amount == 0.0
    assert breakdown.platform_fee == 200.0  # 20% default commission
    assert breakdown.tax_amount == 180.0  # 18% GST on discounted base
    assert breakdown.total_amount == 1180.0
    assert breakdown.professional_payout_amount == 800.0


@pytest.mark.asyncio
async def test_quote_rejects_unknown_coupon(db_session):
    from app.core.exceptions import ValidationAppError

    pricing = PricingService(db_session)
    with pytest.raises(ValidationAppError):
        await pricing.quote(base_price=1000.0, coupon_code="DOES-NOT-EXIST")
