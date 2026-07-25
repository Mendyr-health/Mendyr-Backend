"""Thin wrapper around the Razorpay SDK — order creation, signature verification, refunds."""

import hashlib
import hmac

import razorpay

from app.core.config import settings


class RazorpayClient:
    def __init__(self) -> None:
        self._client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )

    def create_order(
        self, *, amount_rupees: float, receipt: str, notes: dict | None = None
    ) -> dict:
        return self._client.order.create(
            {
                "amount": int(round(amount_rupees * 100)),  # Razorpay expects paise
                "currency": "INR",
                "receipt": receipt,
                "notes": notes or {},
            }
        )

    def verify_payment_signature(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        try:
            self._client.utility.verify_payment_signature(
                {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                }
            )
            return True
        except razorpay.errors.SignatureVerificationError:
            return False

    def verify_webhook_signature(self, *, payload: bytes, signature: str) -> bool:
        expected = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def refund(self, payment_id: str, *, amount_rupees: float | None = None) -> dict:
        payload = {}
        if amount_rupees is not None:
            payload["amount"] = int(round(amount_rupees * 100))
        return self._client.payment.refund(payment_id, payload)
