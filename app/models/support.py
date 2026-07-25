"""Post-booking support / complaint tickets raised by patients or professionals."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import SupportTicketPriority, SupportTicketStatus
from app.db.base_class import Base, TimestampMixin, UUIDPKMixin
from app.db.types import pg_enum


class SupportTicket(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "support_tickets"

    raised_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True
    )
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # billing | quality | safety | app_issue ...
    priority: Mapped[SupportTicketPriority] = mapped_column(
        pg_enum(SupportTicketPriority, "support_ticket_priority"),
        default=SupportTicketPriority.MEDIUM,
        nullable=False,
    )
    status: Mapped[SupportTicketStatus] = mapped_column(
        pg_enum(SupportTicketStatus, "support_ticket_status"),
        default=SupportTicketStatus.OPEN,
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["SupportTicketMessage"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )


class SupportTicketMessage(Base, UUIDPKMixin):
    __tablename__ = "support_ticket_messages"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ticket: Mapped["SupportTicket"] = relationship(back_populates="messages")
