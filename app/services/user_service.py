"""User profile reads/updates and device-token registration for push notifications."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.user import DeviceToken, User
from app.repositories.user_repo import UserRepository
from app.schemas.user import DeviceTokenIn, UserUpdateIn


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def get(self, user_id: uuid.UUID) -> User:
        user = await self.session.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    async def update_profile(self, user_id: uuid.UUID, payload: UserUpdateIn) -> User:
        user = await self.get(user_id)
        updates = payload.model_dump(exclude_unset=True)

        if "email" in updates and updates["email"] != user.email:
            email = (updates["email"] or "").strip().lower() or None
            existing_email_user = await self.users.get_by_email(email) if email else None
            if existing_email_user is not None and existing_email_user.id != user_id:
                raise ConflictError("An account with this email already exists.")
            updates["email"] = email
        if "phone_number" in updates and updates["phone_number"] != user.phone_number:
            existing = await self.users.get_by_phone(updates["phone_number"])
            if existing is not None and existing.id != user_id:
                raise ConflictError("An account with this phone number already exists.")

        for field, value in updates.items():
            setattr(user, field, value)
        await self.session.flush()
        return user

    async def register_device(self, user_id: uuid.UUID, payload: DeviceTokenIn) -> DeviceToken:
        result = await self.session.execute(
            select(DeviceToken).where(
                DeviceToken.user_id == user_id, DeviceToken.push_token == payload.push_token
            )
        )
        device = result.scalar_one_or_none()
        if device is None:
            device = DeviceToken(
                user_id=user_id, push_token=payload.push_token, platform=payload.platform
            )
            self.session.add(device)
        else:
            device.is_active = True
            device.platform = payload.platform
        device.app_version = payload.app_version
        await self.session.flush()
        return device
