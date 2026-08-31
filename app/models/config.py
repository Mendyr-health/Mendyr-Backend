"""Admin-managed key/value config entries used to drive both UI and backend behavior."""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPKMixin


class Config(Base, UUIDPKMixin, TimestampMixin):
    """A single named config entry, e.g. `MAX_BOOKING_RADIUS_KM` or `MAINTENANCE_MODE`."""

    __tablename__ = "configs"

    key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
