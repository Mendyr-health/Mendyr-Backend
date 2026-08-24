"""Contact-us form submissions from the public marketing site (not tied to a user account)."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import ContactInquiryStatus
from app.db.base_class import Base, TimestampMixin, UUIDPKMixin
from app.db.types import pg_enum


class ContactInquiry(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "contact_inquiries"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(15), nullable=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ContactInquiryStatus] = mapped_column(
        pg_enum(ContactInquiryStatus, "contact_inquiry_status"),
        default=ContactInquiryStatus.NEW,
        nullable=False,
    )
