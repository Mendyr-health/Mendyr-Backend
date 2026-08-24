"""Patient <-> professional care-coordination chat. Threads are one-per-(patient,
professional) pair; either side can send once a thread exists (created lazily from an
active booking — see `get_or_create_thread_for_booking`).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.messaging import Message, MessageThread
from app.models.user import User
from app.repositories.booking_repo import BookingRepository
from app.repositories.messaging_repo import MessageRepository, MessageThreadRepository
from app.repositories.professional_repo import ProfessionalRepository
from app.repositories.user_repo import UserRepository
from app.schemas.messaging import MessagePublic, MessageThreadPublic


class MessagingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.threads = MessageThreadRepository(session)
        self.messages = MessageRepository(session)
        self.bookings = BookingRepository(session)
        self.professionals = ProfessionalRepository(session)
        self.users = UserRepository(session)

    async def list_threads_for_user(self, user: User) -> list[MessageThreadPublic]:
        if user.role.value == "professional":
            profile = await self.professionals.get_by_user_id(user.id)
            if profile is None:
                return []
            threads = await self.threads.get_for_professional(profile.id)
        else:
            threads = await self.threads.get_for_patient(user.id)
        return [await self._thread_public(t, viewer_id=user.id) for t in threads]

    async def _thread_public(
        self, thread: MessageThread, *, viewer_id: uuid.UUID
    ) -> MessageThreadPublic:
        patient = await self.users.get(thread.patient_id)
        professional = await self.professionals.get(thread.professional_id)
        professional_user = await self.users.get(professional.user_id) if professional else None
        unread = await self.threads.unread_count(thread.id, for_user_id=viewer_id)
        return MessageThreadPublic(
            id=thread.id,
            booking_id=thread.booking_id,
            patient_id=thread.patient_id,
            patient_name=patient.full_name if patient else "Unknown",
            patient_avatar=patient.avatar_url if patient else None,
            professional_id=thread.professional_id,
            professional_name=professional_user.full_name if professional_user else "Unknown",
            professional_avatar=professional_user.avatar_url if professional_user else None,
            unread_count=unread,
            last_message_at=thread.last_message_at,
            last_message_preview=None,
        )

    async def _assert_participant(self, thread: MessageThread, user: User) -> None:
        if user.role.value == "professional":
            profile = await self.professionals.get_by_user_id(user.id)
            if profile is None or thread.professional_id != profile.id:
                raise ForbiddenError("Not a participant in this thread.")
        elif thread.patient_id != user.id:
            raise ForbiddenError("Not a participant in this thread.")

    async def get_thread_or_404(self, thread_id: uuid.UUID) -> MessageThread:
        thread = await self.threads.get(thread_id)
        if thread is None:
            raise NotFoundError("Conversation not found.")
        return thread

    async def list_messages(
        self, thread_id: uuid.UUID, user: User, *, limit: int, offset: int
    ) -> tuple[list[MessagePublic], int]:
        thread = await self.get_thread_or_404(thread_id)
        await self._assert_participant(thread, user)
        messages, total = await self.messages.list_for_thread(thread_id, limit=limit, offset=offset)
        await self.messages.mark_thread_read(thread_id, for_user_id=user.id)
        return [self._message_public(m, viewer_id=user.id) for m in messages], total

    def _message_public(self, message: Message, *, viewer_id: uuid.UUID) -> MessagePublic:
        return MessagePublic(
            id=message.id,
            thread_id=message.thread_id,
            sender_id=message.sender_id,
            is_mine=message.sender_id == viewer_id,
            body=message.body,
            is_read=message.is_read,
            created_at=message.created_at,
        )

    async def send_message(self, thread_id: uuid.UUID, user: User, body: str) -> MessagePublic:
        thread = await self.get_thread_or_404(thread_id)
        await self._assert_participant(thread, user)

        message = Message(
            thread_id=thread_id, sender_id=user.id, body=body, created_at=datetime.now(UTC)
        )
        self.messages.add(message)
        thread.last_message_at = message.created_at
        await self.session.flush()
        return self._message_public(message, viewer_id=user.id)

    async def get_or_create_thread_for_booking(
        self, booking_id: uuid.UUID, *, viewer_id: uuid.UUID
    ) -> MessageThreadPublic:
        booking = await self.bookings.get(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        if booking.professional_id is None:
            raise NotFoundError("No professional assigned to this booking yet.")

        viewer_profile = await self.professionals.get_by_user_id(viewer_id)
        is_assigned_professional = (
            viewer_profile is not None and viewer_profile.id == booking.professional_id
        )
        if booking.patient_id != viewer_id and not is_assigned_professional:
            raise ForbiddenError("Not a participant in this booking.")

        thread = await self.threads.get_or_create(
            patient_id=booking.patient_id,
            professional_id=booking.professional_id,
            booking_id=booking.id,
        )
        return await self._thread_public(thread, viewer_id=viewer_id)
