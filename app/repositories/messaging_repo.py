import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update

from app.models.messaging import Message, MessageThread
from app.repositories.base import BaseRepository


class MessageThreadRepository(BaseRepository[MessageThread]):
    model = MessageThread

    async def get_for_patient(self, patient_id: uuid.UUID) -> list[MessageThread]:
        result = await self.session.execute(
            select(MessageThread)
            .where(MessageThread.patient_id == patient_id)
            .order_by(MessageThread.last_message_at.desc().nulls_last())
        )
        return list(result.scalars().all())

    async def get_for_professional(self, professional_id: uuid.UUID) -> list[MessageThread]:
        result = await self.session.execute(
            select(MessageThread)
            .where(MessageThread.professional_id == professional_id)
            .order_by(MessageThread.last_message_at.desc().nulls_last())
        )
        return list(result.scalars().all())

    async def get_or_create(
        self, *, patient_id: uuid.UUID, professional_id: uuid.UUID, booking_id: uuid.UUID | None
    ) -> MessageThread:
        result = await self.session.execute(
            select(MessageThread).where(
                MessageThread.patient_id == patient_id,
                MessageThread.professional_id == professional_id,
            )
        )
        thread = result.scalar_one_or_none()
        if thread is None:
            thread = MessageThread(
                patient_id=patient_id, professional_id=professional_id, booking_id=booking_id
            )
            self.add(thread)
            await self.session.flush()
        return thread

    async def unread_count(self, thread_id: uuid.UUID, *, for_user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Message)
            .where(
                Message.thread_id == thread_id,
                Message.is_read.is_(False),
                Message.sender_id != for_user_id,
            )
        )
        return result.scalar_one()


class MessageRepository(BaseRepository[Message]):
    model = Message

    async def list_for_thread(
        self, thread_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[Message], int]:
        total = (
            await self.session.execute(
                select(func.count()).select_from(Message).where(Message.thread_id == thread_id)
            )
        ).scalar_one()
        result = await self.session.execute(
            select(Message)
            .where(Message.thread_id == thread_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        messages = list(result.scalars().all())
        messages.reverse()  # oldest-first for display, even though we paged newest-first
        return messages, total

    async def mark_thread_read(self, thread_id: uuid.UUID, *, for_user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Message)
            .where(
                Message.thread_id == thread_id,
                Message.sender_id != for_user_id,
                Message.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.now(UTC))
        )
