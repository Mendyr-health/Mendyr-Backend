import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.constants import Gender, UserRole, UserStatus
from app.schemas.common import CamelModel, ORMModel


class UserRead(ORMModel):
    id: uuid.UUID
    phone_number: str
    phone_verified: bool
    email: str | None
    full_name: str
    gender: Gender
    avatar_url: str | None
    role: UserRole
    status: UserStatus
    referral_code: str
    created_at: datetime


class UserUpdateIn(BaseModel):
    full_name: str | None = None
    gender: Gender | None = None
    date_of_birth: datetime | None = None
    email: str | None = None
    avatar_url: str | None = None


class DeviceTokenIn(CamelModel):
    platform: str
    push_token: str
    app_version: str | None = None
