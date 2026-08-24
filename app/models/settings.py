"""Platform-wide settings editable from the Super Admin console. Single row (id=1)."""

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin


class PlatformSettings(Base, TimestampMixin):
    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    platform_name: Mapped[str] = mapped_column(String(100), default="Mendyr", nullable=False)
    support_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    support_phone: Mapped[str | None] = mapped_column(String(15), nullable=True)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    new_registrations_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    platform_commission_pct: Mapped[float] = mapped_column(
        Numeric(5, 2), default=20, nullable=False
    )
