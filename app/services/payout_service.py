"""Professional payouts — aggregated on a settlement cycle (weekly, via Celery beat) rather
than paid out per-visit, to keep bank transfer volume/fees manageable.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import BookingStatus, PayoutStatus
from app.models.booking import Booking
from app.models.payment import Payout
from app.models.professional import ProfessionalProfile


class PayoutService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate_payout_for_professional(
        self, professional_id: uuid.UUID, *, period_start: datetime, period_end: datetime
    ) -> Payout | None:
        result = await self.session.execute(
            select(Booking).where(
                Booking.professional_id == professional_id,
                Booking.status == BookingStatus.COMPLETED,
                Booking.scheduled_start_at >= period_start,
                Booking.scheduled_start_at < period_end,
            )
        )
        bookings = list(result.scalars().all())
        if not bookings:
            return None

        gross_amount = sum(float(b.base_price) - float(b.discount_amount) for b in bookings)
        commission_deducted = sum(float(b.platform_fee) for b in bookings)
        net_amount = sum(float(b.professional_payout_amount) for b in bookings)

        payout = Payout(
            professional_id=professional_id,
            period_start=period_start,
            period_end=period_end,
            total_visits=len(bookings),
            gross_amount=round(gross_amount, 2),
            commission_deducted=round(commission_deducted, 2),
            net_amount=round(net_amount, 2),
            status=PayoutStatus.PENDING,
        )
        self.session.add(payout)
        await self.session.flush()
        return payout

    async def generate_weekly_payouts(
        self, *, period_start: datetime, period_end: datetime
    ) -> list[Payout]:
        """Fan-out entry point called by the Celery beat job — one payout row per professional
        who completed at least one visit in the settlement window."""
        result = await self.session.execute(select(ProfessionalProfile.id))
        payouts = []
        for (professional_id,) in result.all():
            payout = await self.generate_payout_for_professional(
                professional_id, period_start=period_start, period_end=period_end
            )
            if payout:
                payouts.append(payout)
        return payouts

    async def mark_paid(self, payout: Payout, *, provider_reference_id: str) -> Payout:
        payout.status = PayoutStatus.PAID
        payout.provider_reference_id = provider_reference_id
        payout.paid_at = datetime.now(UTC)
        await self.session.flush()
        return payout
