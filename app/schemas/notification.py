import uuid
from datetime import datetime

from app.core.constants import NotificationChannel, NotificationStatus
from app.schemas.common import ORMModel


class NotificationRead(ORMModel):
    id: uuid.UUID
    channel: NotificationChannel
    title: str | None
    body: str
    status: NotificationStatus
    read_at: datetime | None
    created_at: datetime
