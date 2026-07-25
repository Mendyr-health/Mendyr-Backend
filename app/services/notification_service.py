"""Fan-out notification sender: writes an in-app `Notification` row and pushes to the user's
registered devices. SMS/email are opt-in per template (booking codes, OTP already has its own
`OTPService` + SMS path) — kept out of the hot booking-creation path here for latency.
"""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import NotificationChannel, NotificationStatus
from app.integrations.push.fcm import FCMPushClient
from app.models.booking import Booking
from app.models.notification import Notification
from app.models.professional import ProfessionalProfile
from app.models.user import DeviceToken


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.fcm = FCMPushClient()

    async def push_to_user(
        self, user_id: uuid.UUID, *, title: str, body: str, data: dict | None = None
    ) -> None:
        notification = Notification(
            user_id=user_id,
            channel=NotificationChannel.PUSH,
            template_key=data.get("template_key", "generic") if data else "generic",
            title=title,
            body=body,
            data=json.dumps(data) if data else None,
            status=NotificationStatus.QUEUED,
            created_at=datetime.now(UTC),
        )
        self.session.add(notification)
        await self.session.flush()

        result = await self.session.execute(
            select(DeviceToken).where(
                DeviceToken.user_id == user_id, DeviceToken.is_active.is_(True)
            )
        )
        devices = result.scalars().all()
        delivered = False
        for device in devices:
            ok = await self.fcm.send(
                push_token=device.push_token, title=title, body=body, data=data
            )
            delivered = delivered or ok

        notification.status = NotificationStatus.SENT if delivered else NotificationStatus.FAILED
        notification.sent_at = datetime.now(UTC) if delivered else None
        await self.session.flush()

    async def notify_new_offer(self, *, professional_id: uuid.UUID, booking: Booking) -> None:
        professional = await self.session.get(ProfessionalProfile, professional_id)
        if professional is None:
            return
        await self.push_to_user(
            professional.user_id,
            title="New booking request",
            body=f"{booking.service_name_snapshot} — respond within 60 seconds.",
            data={"template_key": "offer_received", "booking_id": str(booking.id)},
        )

    async def notify_offer_accepted(self, booking: Booking) -> None:
        await self.push_to_user(
            booking.patient_id,
            title="Professional assigned!",
            body=f"Your {booking.service_name_snapshot} booking has been confirmed.",
            data={"template_key": "booking_confirmed", "booking_id": str(booking.id)},
        )

    async def notify_booking_status(self, booking: Booking, *, title: str, body: str) -> None:
        await self.push_to_user(
            booking.patient_id,
            title=title,
            body=body,
            data={
                "template_key": "booking_status",
                "booking_id": str(booking.id),
                "status": booking.status.value,
            },
        )
