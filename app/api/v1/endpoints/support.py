"""Support tickets raised by patients or professionals."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.support import SupportTicketCreateIn, SupportTicketMessageIn, SupportTicketRead
from app.services.support_service import SupportService

router = APIRouter(prefix="/support/tickets", tags=["support"])


@router.post("", response_model=SupportTicketRead)
async def create_ticket(
    payload: SupportTicketCreateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SupportTicketRead:
    return await SupportService(db).create_ticket(current_user.id, payload)


@router.post("/{ticket_id}/messages")
async def add_message(
    ticket_id: uuid.UUID,
    payload: SupportTicketMessageIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    message = await SupportService(db).add_message(ticket_id, current_user.id, payload)
    return {"id": str(message.id), "message": message.message}
