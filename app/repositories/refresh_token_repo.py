import uuid
from datetime import datetime

from sqlalchemy import select, update

from app.models.user import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def get_by_jti(self, jti: uuid.UUID) -> RefreshToken | None:
        result = await self.session.execute(select(RefreshToken).where(RefreshToken.jti == jti))
        return result.scalar_one_or_none()

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, now: datetime) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
