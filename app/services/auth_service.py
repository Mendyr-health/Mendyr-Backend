"""OTP-first authentication: request code -> verify -> issue JWT pair. Signs up on first verify."""

import secrets
import string
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole
from app.core.exceptions import ValidationAppError
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import TokenPair
from app.services.otp_service import OTPService
from app.services.wallet_service import WalletService

REFERRAL_ALPHABET = string.ascii_uppercase + string.digits


def _generate_referral_code() -> str:
    return "".join(secrets.choice(REFERRAL_ALPHABET) for _ in range(8))


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.otp_service = OTPService(session)
        self.wallet_service = WalletService(session)

    async def request_otp(self, phone_number: str, purpose: str) -> None:
        await self.otp_service.request_otp(phone_number, purpose)

    async def verify_otp_and_authenticate(
        self,
        *,
        phone_number: str,
        code: str,
        purpose: str,
        full_name: str | None,
        role: UserRole | None,
        referral_code: str | None,
    ) -> TokenPair:
        await self.otp_service.verify_otp(phone_number, purpose, code)

        user = await self.users.get_by_phone(phone_number)
        if user is None:
            if not full_name or not role:
                raise ValidationAppError("full_name and role are required for signup.")
            referred_by = None
            if referral_code:
                referred_by = await self.users.get_by_referral_code(referral_code)

            user = User(
                phone_number=phone_number,
                phone_verified=True,
                full_name=full_name,
                role=role,
                referral_code=_generate_referral_code(),
                referred_by_id=referred_by.id if referred_by else None,
            )
            self.users.add(user)
            await self.session.flush()
            await self.wallet_service.get_or_create_wallet(user.id)
        else:
            user.phone_verified = True

        return TokenPair(
            access_token=create_access_token(str(user.id), role=user.role.value),
            refresh_token=create_refresh_token(str(user.id)),
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValidationAppError("Invalid refresh token.")

        user = await self.users.get(uuid.UUID(payload["sub"]))
        if user is None:
            raise ValidationAppError("User no longer exists.")

        return TokenPair(
            access_token=create_access_token(str(user.id), role=user.role.value),
            refresh_token=create_refresh_token(str(user.id)),
        )
