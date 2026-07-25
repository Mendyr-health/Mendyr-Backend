import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.constants import SupportTicketPriority, SupportTicketStatus
from app.schemas.common import ORMModel


class SupportTicketCreateIn(BaseModel):
    subject: str
    category: str
    booking_id: uuid.UUID | None = None
    initial_message: str


class SupportTicketMessageIn(BaseModel):
    message: str
    attachment_url: str | None = None


class SupportTicketRead(ORMModel):
    id: uuid.UUID
    subject: str
    category: str
    priority: SupportTicketPriority
    status: SupportTicketStatus
    created_at: datetime
