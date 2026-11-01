"""The signed-in user's in-app notification inbox. Every push (booking updates, verification
decisions) is also written here, so the apps can show it without a push channel."""

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationRead(BaseModel):
    id: uuid.UUID
    title: str | None
    body: str
    template_key: str
    data: dict | None
    read_at: datetime | None
    created_at: datetime


class NotificationInbox(BaseModel):
    items: list[NotificationRead]
    unread_count: int


@router.get("", response_model=NotificationInbox)
async def list_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    before: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationInbox:
    """Newest first. Page backwards with `before=<created_at of the last item>`."""
    stmt = select(Notification).where(Notification.user_id == current_user.id)
    if before is not None:
        stmt = stmt.where(Notification.created_at < before)
    rows = (
        (await db.execute(stmt.order_by(Notification.created_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    unread = (
        await db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == current_user.id, Notification.read_at.is_(None)
            )
        )
    ).scalar_one()
    return NotificationInbox(
        items=[
            NotificationRead(
                id=n.id,
                title=n.title,
                body=n.body,
                template_key=n.template_key,
                data=json.loads(n.data) if n.data else None,
                read_at=n.read_at,
                created_at=n.created_at,
            )
            for n in rows
        ],
        unread_count=unread,
    )


@router.post("/read-all", response_model=MessageResponse)
async def mark_all_read(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    return MessageResponse(message="All caught up.")


@router.post("/{notification_id}/read", response_model=MessageResponse)
async def mark_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.user_id != current_user.id:
        raise NotFoundError("Notification not found.")
    notification.read_at = notification.read_at or datetime.now(UTC)
    return MessageResponse(message="Marked as read.")
