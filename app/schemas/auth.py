"""OTP-first auth flow: request OTP -> verify OTP -> token pair. Password login is admin-only."""

from pydantic import BaseModel, Field

from app.core.constants import UserRole


class OTPRequestIn(BaseModel):
    phone_number: str = Field(..., pattern=r"^\+?[1-9]\d{9,14}$")
    purpose: str = Field(default="login", pattern="^(login|signup|change_phone)$")


class OTPVerifyIn(BaseModel):
    phone_number: str = Field(..., pattern=r"^\+?[1-9]\d{9,14}$")
    code: str = Field(..., min_length=4, max_length=8)
    purpose: str = Field(default="login", pattern="^(login|signup|change_phone)$")
    # Required only the first time a phone number completes signup:
    full_name: str | None = None
    role: UserRole | None = None
    referral_code: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenIn(BaseModel):
    refresh_token: str


class AdminLoginIn(BaseModel):
    email: str
    password: str
