"""Contact-us inquiry admin lookups (list/search/filter by status, status transitions)."""

from sqlalchemy import func, or_, select

from app.core.constants import ContactInquiryStatus
from app.models.contact import ContactInquiry
from app.repositories.base import BaseRepository


class ContactRepository(BaseRepository[ContactInquiry]):
    model = ContactInquiry

    async def search(
        self,
        *,
        q: str | None,
        status: ContactInquiryStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ContactInquiry], int]:
        stmt = select(ContactInquiry)
        count_stmt = select(func.count(ContactInquiry.id))

        if status is not None:
            stmt = stmt.where(ContactInquiry.status == status)
            count_stmt = count_stmt.where(ContactInquiry.status == status)

        if q:
            like = f"%{q}%"
            search_filter = or_(
                ContactInquiry.name.ilike(like),
                ContactInquiry.email.ilike(like),
                ContactInquiry.subject.ilike(like),
                ContactInquiry.message.ilike(like),
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(ContactInquiry.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def count_by_status(self, status: ContactInquiryStatus) -> int:
        result = await self.session.execute(
            select(func.count(ContactInquiry.id)).where(ContactInquiry.status == status)
        )
        return result.scalar_one()
