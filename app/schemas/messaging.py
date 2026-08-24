"""Care-coordination messaging schemas (app/models/messaging.py's MessageThread/Message).

No corresponding type exists yet in mendyr-frontend/src/types/index.ts — the nurse portal's
Redux mock (src/store/slices/nurseSlice.ts NurseMessageThread/NurseMessage) is the closest
frontend shape, so these mirror it while exposing real ids instead of the mock's literal
'nurse' | 'patient' senderId.
"""

import uuid
from datetime import datetime

from app.schemas.common import CamelModel


class SendMessageIn(CamelModel):
    body: str


class MessagePublic(CamelModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    sender_id: uuid.UUID
    is_mine: bool
    body: str
    is_read: bool
    created_at: datetime


class MessageThreadPublic(CamelModel):
    id: uuid.UUID
    booking_id: uuid.UUID | None
    patient_id: uuid.UUID
    patient_name: str
    patient_avatar: str | None
    professional_id: uuid.UUID
    professional_name: str
    professional_avatar: str | None
    unread_count: int
    last_message_at: datetime | None
    last_message_preview: str | None
