"""Auth-level identity: User, legacy OTP verification records, registered push devices."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DevicePlatform, Gender, UserRole, UserStatus
from app.db.base_class import Base, SoftDeleteMixin, TimestampMixin, UUIDPKMixin
from app.db.types import pg_enum


class User(Base, UUIDPKMixin, TimestampMixin, SoftDeleteMixin):
    """Root identity shared by patients, professionals and internal staff.

    Email + password is the login credential; phone number is an optional profile
    detail collected at signup or added later.
    """

    __tablename__ = "users"

    phone_number: Mapped[str | None] = mapped_column(
        String(15), unique=True, nullable=True, index=True
    )
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    gender: Mapped[Gender] = mapped_column(
        pg_enum(Gender, "gender"), default=Gender.UNSPECIFIED, nullable=False
    )
    date_of_birth: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        pg_enum(UserStatus, "user_status"), default=UserStatus.ACTIVE, nullable=False
    )

    referral_code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    referred_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    patient_profile: Mapped["PatientProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    professional_profile: Mapped["ProfessionalProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    addresses: Mapped[list["Address"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    device_tokens: Mapped[list["DeviceToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_users_role_status", "role", "status"),)


class OTPVerification(Base, UUIDPKMixin):
    """Unused: retained only so the existing otp_verifications table still maps.

    The prototype authenticates with email + password; nothing writes rows here. Drop the
    model and the table together when you're sure no OTP flow is coming back.
    """

    __tablename__ = "otp_verifications"

    phone_number: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # login | signup | change_phone
    hashed_code: Mapped[str] = mapped_column(String(255), nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=5, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_otp_phone_purpose", "phone_number", "purpose"),)


class DeviceToken(Base, UUIDPKMixin, TimestampMixin):
    """FCM push registration — a user may have multiple devices logged in."""

    __tablename__ = "device_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[DevicePlatform] = mapped_column(
        pg_enum(DevicePlatform, "device_platform"), nullable=False
    )
    push_token: Mapped[str] = mapped_column(String(500), nullable=False)
    app_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="device_tokens")

    __table_args__ = (Index("uq_device_tokens_user_token", "user_id", "push_token", unique=True),)
