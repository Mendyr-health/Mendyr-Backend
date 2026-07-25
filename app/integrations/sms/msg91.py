"""MSG91 SMS/OTP provider — production SMS for Indian phone numbers."""

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

MSG91_BASE_URL = "https://control.msg91.com/api/v5"


class MSG91SMSProvider:
    async def send_otp(self, phone_number: str, code: str) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{MSG91_BASE_URL}/otp",
                params={
                    "authkey": settings.MSG91_AUTH_KEY,
                    "template_id": settings.MSG91_OTP_TEMPLATE_ID,
                    "mobile": phone_number,
                    "otp": code,
                },
            )
            if response.status_code >= 400:
                logger.error(
                    "msg91_send_otp_failed", status=response.status_code, body=response.text
                )
                response.raise_for_status()

    async def send_message(self, phone_number: str, message: str) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{MSG91_BASE_URL}/flow",
                headers={"authkey": settings.MSG91_AUTH_KEY},
                json={
                    "sender": settings.MSG91_SENDER_ID,
                    "mobiles": phone_number,
                    "message": message,
                },
            )
            if response.status_code >= 400:
                logger.error(
                    "msg91_send_message_failed", status=response.status_code, body=response.text
                )
                response.raise_for_status()
