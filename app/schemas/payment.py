import uuid

from pydantic import BaseModel

from app.core.constants import PaymentStatus
from app.schemas.common import ORMModel


class PaymentOrderCreateIn(BaseModel):
    booking_id: uuid.UUID


class PaymentOrderOut(BaseModel):
    """Everything the mobile SDK's Razorpay checkout needs to open the payment sheet."""

    provider_order_id: str
    amount: float
    currency: str
    razorpay_key_id: str
    booking_id: uuid.UUID


class PaymentVerifyIn(BaseModel):
    booking_id: uuid.UUID
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentRead(ORMModel):
    id: uuid.UUID
    status: PaymentStatus
    amount: float
    amount_refunded: float
    currency: str
