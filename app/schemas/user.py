import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import Gender, UserRole, UserStatus
from app.schemas.common import ORMModel


class UserRead(ORMModel):
    id: uuid.UUID
    phone_number: str
    phone_verified: bool
    email: str | None
    email_verified: bool
    full_name: str
    gender: Gender
    date_of_birth: datetime | None
    avatar_url: str | None
    role: UserRole
    status: UserStatus
    referral_code: str
    last_login_at: datetime | None
    created_at: datetime


class UserUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    gender: Gender | None = None
    date_of_birth: datetime | None = None
    email: str | None = None
    phone_number: str | None = Field(default=None, pattern=r"^\+?[1-9]\d{9,14}$")
    avatar_url: str | None = None


class DeviceTokenIn(BaseModel):
    platform: str
    push_token: str
    app_version: str | None = None
