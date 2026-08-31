"""Email + password authentication: register / login -> JWT pair, plus refresh-token exchange."""

import secrets
import string
import uuid
from datetime import UTC, datetime

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import Gender, UserRole, UserStatus
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import TokenPair
from app.services.wallet_service import WalletService

REFERRAL_ALPHABET = string.ascii_uppercase + string.digits

# Deliberately identical for "no such email" and "wrong password" so the endpoint can't be
# used to enumerate which email addresses have accounts.
_BAD_CREDENTIALS = "Incorrect email or password."


def _generate_referral_code() -> str:
    return "".join(secrets.choice(REFERRAL_ALPHABET) for _ in range(8))


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.wallet_service = WalletService(session)

    def _issue_pair(self, user: User) -> TokenPair:
        return TokenPair(
            access_token=create_access_token(str(user.id), role=user.role.value),
            refresh_token=create_refresh_token(str(user.id)),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        role: UserRole,
        phone_number: str,
        gender: Gender | None = None,
        referral_code: str | None = None,
    ) -> TokenPair:
        email = email.strip().lower()

        if await self.users.get_by_email(email) is not None:
            raise ConflictError("An account with this email already exists.")
        if await self.users.get_by_phone(phone_number) is not None:
            raise ConflictError("An account with this phone number already exists.")

        referred_by = (
            await self.users.get_by_referral_code(referral_code) if referral_code else None
        )

        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
            phone_number=phone_number,
            gender=gender or Gender.UNSPECIFIED,
            referral_code=_generate_referral_code(),
            referred_by_id=referred_by.id if referred_by else None,
            last_login_at=datetime.now(UTC),
        )
        self.users.add(user)
        await self.session.flush()
        await self.wallet_service.get_or_create_wallet(user.id)

        return self._issue_pair(user)

    async def login(self, *, email: str, password: str) -> TokenPair:
        user = await self.users.get_by_email(email.strip().lower())

        # Hash a dummy password when the user doesn't exist so both branches cost the same
        # ~argon2 time — otherwise response latency reveals whether the email is registered.
        if user is None or not user.hashed_password:
            hash_password(password)
            raise UnauthorizedError(_BAD_CREDENTIALS)
        if not verify_password(password, user.hashed_password):
            raise UnauthorizedError(_BAD_CREDENTIALS)
        if user.status is not UserStatus.ACTIVE:
            raise UnauthorizedError("This account is not active. Please contact support.")

        user.last_login_at = datetime.now(UTC)
        await self.session.flush()
        return self._issue_pair(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Exchange a valid refresh token for a fresh access+refresh pair."""
        try:
            payload = decode_token(refresh_token)
        except jwt.ExpiredSignatureError as exc:
            raise UnauthorizedError("Refresh token has expired. Please log in again.") from exc
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid refresh token.") from exc

        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type.")

        try:
            user_id = uuid.UUID(payload["sub"])
        except (KeyError, ValueError) as exc:
            raise UnauthorizedError("Invalid refresh token.") from exc

        user = await self.users.get(user_id)
        if user is None:
            raise UnauthorizedError("User no longer exists.")
        if user.status is not UserStatus.ACTIVE:
            raise UnauthorizedError("This account is not active. Please contact support.")

        return self._issue_pair(user)
