"""Pre-launch waitlist admin lookups (list/search, mark-notified)."""

from sqlalchemy import func, or_, select

from app.models.waitlist import WaitlistEntry
from app.repositories.base import BaseRepository


class WaitlistRepository(BaseRepository[WaitlistEntry]):
    model = WaitlistEntry

    async def search(
        self, *, q: str | None, limit: int, offset: int
    ) -> tuple[list[WaitlistEntry], int]:
        stmt = select(WaitlistEntry)
        count_stmt = select(func.count(WaitlistEntry.id))

        if q:
            like = f"%{q}%"
            search_filter = or_(
                WaitlistEntry.email.ilike(like),
                WaitlistEntry.name.ilike(like),
                WaitlistEntry.phone.ilike(like),
                WaitlistEntry.source.ilike(like),
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(WaitlistEntry.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count(WaitlistEntry.id)))
        return result.scalar_one()
