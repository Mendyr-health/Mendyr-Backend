"""Email + password auth flow: register / login -> JWT pair, refreshable.

`RegisterIn` is deliberately tolerant of the exact payload shapes the Next.js frontend sends
(camelCase field names, an uppercase `role` string, a `NURSE` role that has no backing
`UserRole` member) rather than requiring the frontend to change — see `_adapt_frontend_payload`.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.constants import Gender, UserRole
from app.schemas.user import UserRead

# Self-registration must never be able to mint an admin/ops account — those are only ever
# created via `scripts/create_admin.py`, run by someone with direct database access.
SELF_REGISTERABLE_ROLES = (UserRole.PATIENT, UserRole.PROFESSIONAL)

# The frontend's registration forms send `role: 'NURSE'` — there is no `UserRole.NURSE`
# (nurse/physio/caretaker/etc. is `ProfessionalType`, chosen later during KYC onboarding, not
# at signup) — so any alias here collapses to the account-level role it actually creates.
_ROLE_ALIASES = {"NURSE": "professional", "PATIENT": "patient", "PROFESSIONAL": "professional"}

# apps/patient/.../register/nurse's gender options include PREFER_NOT_TO_SAY, which has no
# matching Gender member — it maps to the closest existing value.
_GENDER_ALIASES = {
    "MALE": "male",
    "FEMALE": "female",
    "OTHER": "other",
    "PREFER_NOT_TO_SAY": "unspecified",
}

# Fields the frontend sends that aren't first-class User columns (profile/address/professional
# details) — captured into `extended_attributes` verbatim rather than silently dropped.
_EXTRA_ATTRIBUTE_KEYS = (
    "address",
    "city",
    "state",
    "experience",
    "qualifications",
    "certifications",
    "preferredContact",
)


class RegisterIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=150, alias="fullName")
    role: UserRole = UserRole.PATIENT
    # Required and unique — `users.phone_number` is NOT NULL UNIQUE in the schema, so a
    # missing number must fail validation here (422) rather than at INSERT time (500).
    phone_number: str = Field(..., pattern=r"^\+?[1-9]\d{9,14}$", alias="phone")
    gender: Gender | None = None
    date_of_birth: datetime | None = Field(default=None, alias="dob")
    referral_code: str | None = None
    # Free-form additional data — no schema enforcement, same JSONB column the config-driven
    # extended_attributes on the other domain tables use. Also where `_adapt_frontend_payload`
    # stashes fields like address/city/state/experience that aren't first-class User columns.
    extended_attributes: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _adapt_frontend_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)

        # Patient form sends `dob`, nurse form sends `dateOfBirth` — the `dob` alias above
        # only covers the first; fold the second in under the same key before aliasing runs.
        if "dateOfBirth" in data and "dob" not in data and "date_of_birth" not in data:
            data["dob"] = data.pop("dateOfBirth")

        if isinstance(data.get("role"), str):
            original_role = data["role"]
            mapped = _ROLE_ALIASES.get(original_role.strip().upper())
            if mapped is not None:
                data["role"] = mapped
            if original_role.strip().upper() == "NURSE":
                # The account is created as `professional`; the requested specialization is
                # preserved here for whoever builds the KYC-onboarding step to default from.
                data.setdefault("extended_attributes", {})
                data["extended_attributes"]["requested_professional_type"] = "nurse"

        if isinstance(data.get("gender"), str):
            mapped_gender = _GENDER_ALIASES.get(data["gender"].strip().upper())
            if mapped_gender is not None:
                data["gender"] = mapped_gender

        extras = {k: data.pop(k) for k in _EXTRA_ATTRIBUTE_KEYS if k in data}
        if extras:
            merged = dict(data.get("extended_attributes") or {})
            merged.update(extras)
            data["extended_attributes"] = merged

        return data

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
    # The frontend is cookie-only and never reads the tokens above — it reads this instead
    # (`data.data.user.role` right after login/register) to route to the right dashboard
    # without a second round trip to /me.
    user: UserRead


class RefreshTokenIn(BaseModel):
    refresh_token: str
