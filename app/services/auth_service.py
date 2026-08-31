"""Email + password authentication: register / login -> JWT pair, plus refresh-token exchange."""

import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta

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
from app.models.user import RefreshToken, User
from app.repositories.refresh_token_repo import RefreshTokenRepository
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
        self.refresh_tokens = RefreshTokenRepository(session)
        self.wallet_service = WalletService(session)

    async def _issue_pair(self, user: User) -> TokenPair:
        jti = uuid.uuid4()
        now = datetime.now(UTC)
        self.refresh_tokens.add(
            RefreshToken(
                user_id=user.id,
                jti=jti,
                issued_at=now,
                expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            )
        )
        await self.session.flush()

        return TokenPair(
            access_token=create_access_token(str(user.id), role=user.role.value),
            refresh_token=create_refresh_token(str(user.id), jti=str(jti)),
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
        date_of_birth: datetime | None = None,
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
            date_of_birth=date_of_birth,
            referral_code=_generate_referral_code(),
            referred_by_id=referred_by.id if referred_by else None,
            last_login_at=datetime.now(UTC),
        )
        self.users.add(user)
        await self.session.flush()
        await self.wallet_service.get_or_create_wallet(user.id)

        return await self._issue_pair(user)

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
        return await self._issue_pair(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Exchange a valid, not-yet-used refresh token for a fresh access+refresh pair.

        Refresh tokens rotate on every use: the presented token is marked revoked and a new
        one is issued in its place. If an already-revoked token is presented again — the
        signal for a leaked token being replayed after the legitimate client already rotated
        past it — every active refresh token for that user is revoked, forcing a full
        re-login everywhere.
        """
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
            jti = uuid.UUID(payload["jti"])
        except (KeyError, ValueError) as exc:
            raise UnauthorizedError("Invalid refresh token.") from exc

        user = await self.users.get(user_id)
        if user is None:
            raise UnauthorizedError("User no longer exists.")
        if user.status is not UserStatus.ACTIVE:
            raise UnauthorizedError("This account is not active. Please contact support.")

        token_record = await self.refresh_tokens.get_by_jti(jti)
        if token_record is None:
            raise UnauthorizedError("Invalid refresh token.")

        now = datetime.now(UTC)
        if token_record.revoked_at is not None:
            await self.refresh_tokens.revoke_all_for_user(user.id, now=now)
            await self.session.flush()
            raise UnauthorizedError(
                "This refresh token has already been used. All sessions have been revoked "
                "for security — please log in again."
            )
        if token_record.expires_at < now:
            raise UnauthorizedError("Refresh token has expired. Please log in again.")

        token_record.revoked_at = now
        new_pair = await self._issue_pair(user)
        token_record.replaced_by_jti = uuid.UUID(decode_token(new_pair.refresh_token)["jti"])
        await self.session.flush()
        return new_pair
