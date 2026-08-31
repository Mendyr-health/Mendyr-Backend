"""Email + password auth flow: register / login -> JWT pair, refreshable."""

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.constants import Gender, UserRole

# Self-registration must never be able to mint an admin/ops account — those are only ever
# created via `scripts/create_admin.py`, run by someone with direct database access.
SELF_REGISTERABLE_ROLES = (UserRole.PATIENT, UserRole.PROFESSIONAL)


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

    @field_validator("role")
    @classmethod
    def _role_must_be_self_registerable(cls, value: UserRole) -> UserRole:
        if value not in SELF_REGISTERABLE_ROLES:
            allowed = ", ".join(r.value for r in SELF_REGISTERABLE_ROLES)
            raise ValueError(f"role must be one of: {allowed}")
        return value


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
