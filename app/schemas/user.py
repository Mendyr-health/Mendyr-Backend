import uuid
from datetime import datetime

from pydantic import BaseModel

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
    full_name: str | None = None
    gender: Gender | None = None
    date_of_birth: datetime | None = None
    email: str | None = None
    avatar_url: str | None = None


class DeviceTokenIn(BaseModel):
    platform: str
    push_token: str
    app_version: str | None = None
