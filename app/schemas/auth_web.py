"""Email/password auth schemas for the Next.js frontend (src/types/index.ts) — camelCase,
served under /api/auth/* (no /v1 prefix, matching exactly what the frontend calls).

Separate from app/schemas/auth.py, which is the OTP-first mobile-native flow returning
bearer tokens in the response body. This flow instead sets the tokens as httpOnly cookies
(see app/core/cookies.py) and mirrors the ApiResponse<T> envelope the frontend expects.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from app.core.constants import UserRole
from app.schemas.common import CamelModel, CamelORMModel


class LoginIn(CamelModel):
    email: EmailStr
    password: str


class RegisterIn(CamelModel):
    role: Literal["PATIENT", "NURSE"]
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str
    password: str = Field(min_length=8, max_length=128)
    address: str | None = None
    city: str | None = None
    state: str | None = None

    # Nurse-only fields (validated as required for role=NURSE in the service layer —
    # Pydantic's discriminated unions don't play well with a single flat frontend payload).
    gender: str | None = None
    date_of_birth: str | None = None
    experience: str | None = None
    qualifications: str | None = None
    certifications: str | None = None
    preferred_contact: str | None = None


class UserPublicOut(CamelORMModel):
    # UUID (not str) so Pydantic serializes it directly — a plain `str` field would reject
    # the ORM's UUID attribute outright under from_attributes population.
    public_id: uuid.UUID = Field(validation_alias="id", serialization_alias="publicId")
    email: str
    phone: str | None
    full_name: str
    role: UserRole
    status: str
    email_verified: bool
    avatar_url: str | None
    last_login_at: datetime | None
    created_at: datetime


class AuthResultOut(CamelModel):
    user: UserPublicOut
