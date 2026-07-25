"""Post-booking support tickets — patient/professional complaints and billing/safety issues."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import SupportTicketStatus
from app.core.exceptions import NotFoundError
from app.models.support import SupportTicket, SupportTicketMessage
from app.schemas.support import SupportTicketCreateIn, SupportTicketMessageIn


class SupportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_ticket(
        self, raised_by_id: uuid.UUID, payload: SupportTicketCreateIn
    ) -> SupportTicket:
        ticket = SupportTicket(
            raised_by_id=raised_by_id,
            booking_id=payload.booking_id,
            subject=payload.subject,
            category=payload.category,
            status=SupportTicketStatus.OPEN,
        )
        self.session.add(ticket)
        await self.session.flush()

        self.session.add(
            SupportTicketMessage(
                ticket_id=ticket.id,
                sender_id=raised_by_id,
                message=payload.initial_message,
                created_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        return ticket

    async def add_message(
        self, ticket_id: uuid.UUID, sender_id: uuid.UUID, payload: SupportTicketMessageIn
    ) -> SupportTicketMessage:
        ticket = await self.session.get(SupportTicket, ticket_id)
        if ticket is None:
            raise NotFoundError("Support ticket not found.")

        message = SupportTicketMessage(
            ticket_id=ticket_id,
            sender_id=sender_id,
            message=payload.message,
            attachment_url=payload.attachment_url,
            created_at=datetime.now(UTC),
        )
        self.session.add(message)
        if ticket.status == SupportTicketStatus.RESOLVED:
            ticket.status = SupportTicketStatus.IN_PROGRESS
        await self.session.flush()
        return message

    async def update_status(
        self, ticket_id: uuid.UUID, status: SupportTicketStatus
    ) -> SupportTicket:
        ticket = await self.session.get(SupportTicket, ticket_id)
        if ticket is None:
            raise NotFoundError("Support ticket not found.")
        ticket.status = status
        if status in (SupportTicketStatus.RESOLVED, SupportTicketStatus.CLOSED):
            ticket.resolved_at = datetime.now(UTC)
        await self.session.flush()
        return ticket
