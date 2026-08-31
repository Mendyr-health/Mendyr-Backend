"""Email + password auth flow: register / login -> JWT pair, refreshable."""

from pydantic import BaseModel, EmailStr, Field

from app.core.constants import Gender, UserRole


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=150)
    role: UserRole = UserRole.PATIENT
    # Required and unique — `users.phone_number` is NOT NULL UNIQUE in the schema, so a
    # missing number must fail validation here (422) rather than at INSERT time (500).
    phone_number: str = Field(..., pattern=r"^\+?[1-9]\d{9,14}$")
    gender: Gender | None = None
    referral_code: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access-token lifetime in seconds, so the client can pre-emptively refresh


class RefreshTokenIn(BaseModel):
    refresh_token: str
