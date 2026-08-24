"""Two authentication flows share this service:

- OTP-first (mobile-native, request/verify/refresh) — returns bearer tokens in the body.
- Email/password (the Next.js frontend, login/register/refresh) — sets httpOnly cookies.
  See app/api/web/auth.py. Both converge on the same User model / token issuance.
"""

import secrets
import string
import uuid
from contextlib import suppress
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import Gender, PreferredContactMethod, ProfessionalType, UserRole
from app.core.exceptions import ConflictError, UnauthorizedError, ValidationAppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.patient import PatientProfile
from app.models.professional import ProfessionalProfile
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import TokenPair
from app.schemas.auth_web import RegisterIn
from app.services.otp_service import OTPService
from app.services.wallet_service import WalletService

REFERRAL_ALPHABET = string.ascii_uppercase + string.digits


def _generate_referral_code() -> str:
    return "".join(secrets.choice(REFERRAL_ALPHABET) for _ in range(8))


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationAppError(f"Invalid date: {value!r}, expected YYYY-MM-DD.") from exc


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.otp_service = OTPService(session)
        self.wallet_service = WalletService(session)

    # ── Email/password (web + Capacitor app) ─────────────────────────────

    async def login_with_password(self, email: str, password: str) -> User:
        user = await self.users.get_by_email(email)
        if user is None or not user.hashed_password:
            raise UnauthorizedError("Invalid email or password.")
        if not verify_password(password, user.hashed_password):
            raise UnauthorizedError("Invalid email or password.")
        user.last_login_at = datetime.now(UTC)
        return user

    async def register(self, payload: RegisterIn) -> User:
        if await self.users.get_by_email(payload.email):
            raise ConflictError("An account with this email already exists.")

        role = UserRole.PATIENT if payload.role == "PATIENT" else UserRole.PROFESSIONAL
        gender = Gender.UNSPECIFIED
        if payload.gender:
            with suppress(ValueError):
                gender = Gender(payload.gender.lower())

        user = User(
            email=payload.email,
            phone_number=payload.phone,
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
            role=role,
            gender=gender,
            date_of_birth=_parse_date(payload.date_of_birth),
            referral_code=_generate_referral_code(),
        )
        self.users.add(user)
        await self.session.flush()
        await self.wallet_service.get_or_create_wallet(user.id)

        if role == UserRole.PATIENT:
            self.session.add(
                PatientProfile(
                    user_id=user.id,
                    address_line=payload.address,
                    city=payload.city,
                    state=payload.state,
                )
            )
        else:
            preferred_contact = PreferredContactMethod.EMAIL
            if payload.preferred_contact:
                with suppress(ValueError):
                    preferred_contact = PreferredContactMethod(payload.preferred_contact.lower())
            self.session.add(
                ProfessionalProfile(
                    user_id=user.id,
                    professional_type=ProfessionalType.NURSE,
                    address_line=payload.address,
                    city=payload.city,
                    state=payload.state,
                    experience_description=payload.experience,
                    qualifications=payload.qualifications,
                    certifications=payload.certifications,
                    preferred_contact=preferred_contact,
                )
            )

        await self.session.flush()
        return user

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
