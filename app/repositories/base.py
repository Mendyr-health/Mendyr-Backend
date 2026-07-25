"""Generic async repository — thin CRUD wrapper shared by every domain repo.

Domain-specific repositories (matching, booking dispatch, wallet ledger) subclass this
and add hand-written queries; simple lookups (service catalogue, coupons, addresses)
use `BaseRepository` directly from the service layer without a dedicated subclass.
"""

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base_class import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id_: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, id_)

    async def list(self, *, limit: int = 20, offset: int = 0) -> list[ModelT]:
        result = await self.session.execute(select(self.model).limit(limit).offset(offset))
        return list(result.scalars().all())

    def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)

    async def flush(self) -> None:
        await self.session.flush()
