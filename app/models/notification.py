"""Outbound notification log — every push/SMS/email/in-app message sent to a user."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import NotificationChannel, NotificationStatus
from app.db.base_class import Base, UUIDPKMixin
from app.db.types import pg_enum


class Notification(Base, UUIDPKMixin):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        pg_enum(NotificationChannel, "notification_channel"), nullable=False
    )
    template_key: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g. booking_confirmed, offer_received
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON string payload for deep-linking

    status: Mapped[NotificationStatus] = mapped_column(
        pg_enum(NotificationStatus, "notification_status"),
        default=NotificationStatus.QUEUED,
        nullable=False,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
