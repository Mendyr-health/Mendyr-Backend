"""Razorpay order creation, payment verification/capture, webhook processing and refunds.

On successful capture this kicks off dispatch (`MatchingService.start_dispatch`) — a booking
only enters the SEARCHING queue once money has actually moved, so professionals are never
offered a booking the patient hasn't paid for.
"""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import BookingStatus, PaymentStatus
from app.core.exceptions import ForbiddenError, NotFoundError, PaymentError, ValidationAppError
from app.integrations.razorpay_client import RazorpayClient
from app.models.booking import Booking
from app.models.payment import Payment
from app.repositories.booking_repo import BookingRepository
from app.services.booking_service import BookingService
from app.services.matching_service import MatchingService


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.bookings = BookingRepository(session)
        self.booking_service = BookingService(session)
        self.matching_service = MatchingService(session)
        self.razorpay = RazorpayClient()

    async def create_order(
        self, *, booking_id: uuid.UUID, patient_id: uuid.UUID
    ) -> tuple[Payment, str]:
        booking = await self.bookings.get(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        if booking.patient_id != patient_id:
            raise ForbiddenError("This booking does not belong to you.")
        if booking.status != BookingStatus.CREATED:
            raise ValidationAppError("This booking has already been paid or is no longer payable.")

        order = self.razorpay.create_order(
            amount_rupees=float(booking.total_amount),
            receipt=booking.booking_code,
            notes={"booking_id": str(booking.id)},
        )
        payment = Payment(
            booking_id=booking.id,
            patient_id=patient_id,
            provider_order_id=order["id"],
            status=PaymentStatus.PENDING,
            amount=float(booking.total_amount),
        )
        self.session.add(payment)
        await self.session.flush()
        return payment, order["id"]

    async def verify_and_capture(
        self, *, booking_id: uuid.UUID, order_id: str, payment_id: str, signature: str
    ) -> Booking:
        if not self.razorpay.verify_payment_signature(
            order_id=order_id, payment_id=payment_id, signature=signature
        ):
            raise PaymentError("Payment signature verification failed.")

        result = await self.session.execute(
            select(Payment).where(Payment.provider_order_id == order_id)
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            raise NotFoundError("Payment record not found for this order.")

        payment.provider_payment_id = payment_id
        payment.provider_signature = signature
        payment.status = PaymentStatus.CAPTURED
        payment.captured_at = datetime.now(UTC)

        booking = await self.bookings.get(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")

        await self.booking_service.transition_status(
            booking, BookingStatus.SEARCHING, reason="Payment captured"
        )
        await self.session.flush()
        await self.matching_service.start_dispatch(booking.id)
        return booking

    async def handle_webhook(self, *, payload: bytes, signature: str) -> None:
        """Idempotent fallback path — Razorpay may deliver this even if the client-side
        `verify_and_capture` call already ran; every branch here is safe to run twice."""
        if not self.razorpay.verify_webhook_signature(payload=payload, signature=signature):
            raise PaymentError("Invalid webhook signature.")

        event = json.loads(payload)
        event_type = event.get("event")
        entity = event.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = entity.get("order_id")
        if not order_id:
            return

        result = await self.session.execute(
            select(Payment).where(Payment.provider_order_id == order_id)
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            return

        payment.raw_webhook_payload = json.dumps(event)

        if event_type == "payment.captured" and payment.status != PaymentStatus.CAPTURED:
            payment.status = PaymentStatus.CAPTURED
            payment.provider_payment_id = entity.get("id")
            payment.captured_at = datetime.now(UTC)
            booking = await self.bookings.get(payment.booking_id)
            if booking and booking.status == BookingStatus.CREATED:
                await self.booking_service.transition_status(
                    booking, BookingStatus.SEARCHING, reason="Payment captured (webhook)"
                )
                await self.session.flush()
                await self.matching_service.start_dispatch(booking.id)
        elif event_type == "payment.failed":
            payment.status = PaymentStatus.FAILED
            payment.failure_reason = entity.get("error_description")

        await self.session.flush()

    async def refund(self, booking: Booking, *, amount: float | None = None) -> None:
        result = await self.session.execute(
            select(Payment).where(
                Payment.booking_id == booking.id, Payment.status == PaymentStatus.CAPTURED
            )
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            return  # nothing captured yet — no refund needed

        refund_amount = amount if amount is not None else float(payment.amount)
        self.razorpay.refund(payment.provider_payment_id, amount_rupees=refund_amount)

        payment.amount_refunded = float(payment.amount_refunded) + refund_amount
        payment.status = (
            PaymentStatus.REFUNDED
            if payment.amount_refunded >= float(payment.amount)
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        payment.refunded_at = datetime.now(UTC)
        await self.session.flush()
