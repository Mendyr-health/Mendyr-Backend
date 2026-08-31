from sqlalchemy import select

from app.models.config import Config
from app.repositories.base import BaseRepository


class ConfigRepository(BaseRepository[Config]):
    model = Config

    async def get_by_key(self, key: str) -> Config | None:
        result = await self.session.execute(select(Config).where(Config.key == key))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Config]:
        result = await self.session.execute(select(Config).order_by(Config.key))
        return list(result.scalars().all())
