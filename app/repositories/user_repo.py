from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_phone(self, phone_number: str) -> User | None:
        result = await self.session.execute(select(User).where(User.phone_number == phone_number))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_referral_code(self, code: str) -> User | None:
        result = await self.session.execute(select(User).where(User.referral_code == code))
        return result.scalar_one_or_none()
