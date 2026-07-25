"""Local/dev provider — prints the OTP to logs instead of sending a real SMS."""

from app.core.logging import get_logger

logger = get_logger(__name__)


class ConsoleSMSProvider:
    async def send_otp(self, phone_number: str, code: str) -> None:
        logger.info("sms_otp_dev_console", phone_number=phone_number, code=code)

    async def send_message(self, phone_number: str, message: str) -> None:
        logger.info("sms_message_dev_console", phone_number=phone_number, message=message)
