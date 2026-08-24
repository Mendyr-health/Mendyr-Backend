"""Pre-launch waitlist signups from the public marketing site."""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPKMixin


class WaitlistEntry(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "waitlist_entries"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(15), nullable=True)
    # e.g. landing_page, referral
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
