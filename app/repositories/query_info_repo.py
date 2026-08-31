from sqlalchemy import select

from app.models.query_info import QueryInfo
from app.repositories.base import BaseRepository


class QueryInfoRepository(BaseRepository[QueryInfo]):
    model = QueryInfo

    async def get_by_name(self, name: str) -> QueryInfo | None:
        result = await self.session.execute(select(QueryInfo).where(QueryInfo.name == name))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[QueryInfo]:
        result = await self.session.execute(select(QueryInfo).order_by(QueryInfo.name))
        return list(result.scalars().all())
