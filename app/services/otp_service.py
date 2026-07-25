"""OTP generation, hashing, verification and resend throttling.

OTP rows are persisted (not Redis-only) so support/fraud teams retain an audit trail of every
login attempt; Redis is layered on top only for the resend cooldown counter.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import RateLimitedError, ValidationAppError
from app.db.redis import get_redis
from app.integrations.sms import get_sms_provider
from app.models.user import OTPVerification


def _hash_code(phone_number: str, code: str) -> str:
    return hashlib.sha256(f"{phone_number}:{code}:{settings.SECRET_KEY}".encode()).hexdigest()


class OTPService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.redis = get_redis()
        self.sms = get_sms_provider()

    def _cooldown_key(self, phone_number: str, purpose: str) -> str:
        return f"otp:cooldown:{purpose}:{phone_number}"

    async def request_otp(self, phone_number: str, purpose: str) -> None:
        if await self.redis.get(self._cooldown_key(phone_number, purpose)):
            raise RateLimitedError("Please wait before requesting another OTP.")

        code = f"{secrets.randbelow(10**settings.OTP_LENGTH):0{settings.OTP_LENGTH}d}"
        now = datetime.now(UTC)

        otp_row = OTPVerification(
            phone_number=phone_number,
            purpose=purpose,
            hashed_code=_hash_code(phone_number, code),
            max_attempts=settings.OTP_MAX_ATTEMPTS,
            expires_at=now + timedelta(seconds=settings.OTP_TTL_SECONDS),
            created_at=now,
        )
        self.session.add(otp_row)
        await self.session.flush()

        await self.redis.set(
            self._cooldown_key(phone_number, purpose), "1", ex=settings.OTP_RESEND_COOLDOWN_SECONDS
        )
        await self.sms.send_otp(phone_number, code)

    async def verify_otp(self, phone_number: str, purpose: str, code: str) -> None:
        """Raises ValidationAppError on wrong/expired/exhausted code. No return value —
        callers should proceed with login/signup once this doesn't raise."""
        if settings.ENVIRONMENT == "local" and code == settings.OTP_DEV_BYPASS_CODE:
            return

        result = await self.session.execute(
            select(OTPVerification)
            .where(
                OTPVerification.phone_number == phone_number,
                OTPVerification.purpose == purpose,
                OTPVerification.verified.is_(False),
            )
            .order_by(OTPVerification.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        otp_row = result.scalar_one_or_none()
        if otp_row is None:
            raise ValidationAppError("No OTP request found. Please request a new code.")

        now = datetime.now(UTC)
        if otp_row.expires_at.replace(tzinfo=UTC) < now:
            raise ValidationAppError("OTP has expired. Please request a new code.")
        if otp_row.attempts >= otp_row.max_attempts:
            raise ValidationAppError("Too many incorrect attempts. Please request a new code.")

        if otp_row.hashed_code != _hash_code(phone_number, code):
            otp_row.attempts += 1
            await self.session.flush()
            raise ValidationAppError("Incorrect OTP.")

        otp_row.verified = True
        await self.session.flush()
