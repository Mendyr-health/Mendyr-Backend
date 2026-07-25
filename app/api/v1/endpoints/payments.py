"""Razorpay order creation + client-side payment verification."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.permissions import require_patient
from app.db.session import get_db
from app.models.user import User
from app.schemas.booking import BookingRead
from app.schemas.payment import PaymentOrderCreateIn, PaymentOrderOut, PaymentVerifyIn
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/orders", response_model=PaymentOrderOut)
async def create_payment_order(
    payload: PaymentOrderCreateIn,
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> PaymentOrderOut:
    payment, order_id = await PaymentService(db).create_order(
        booking_id=payload.booking_id, patient_id=current_user.id
    )
    return PaymentOrderOut(
        provider_order_id=order_id,
        amount=float(payment.amount),
        currency=payment.currency,
        razorpay_key_id=settings.RAZORPAY_KEY_ID,
        booking_id=payload.booking_id,
    )


@router.post("/verify", response_model=BookingRead)
async def verify_payment(
    payload: PaymentVerifyIn,
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    return await PaymentService(db).verify_and_capture(
        booking_id=payload.booking_id,
        order_id=payload.razorpay_order_id,
        payment_id=payload.razorpay_payment_id,
        signature=payload.razorpay_signature,
    )
