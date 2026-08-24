"""Repositories backing the Super Admin console: admin-user search, audit log listing with
actor join, and singleton platform settings lookup.
"""

from sqlalchemy import func, or_, select

from app.core.constants import UserRole
from app.models.audit import AuditLog
from app.models.settings import PlatformSettings
from app.models.user import User
from app.repositories.base import BaseRepository


class AdminRepository(BaseRepository[User]):
    model = User

    async def search_admins(
        self, *, query: str | None, limit: int, offset: int
    ) -> tuple[list[User], int]:
        stmt = select(User).where(User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
        if query:
            like = f"%{query}%"
            stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like)))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def count_by_role(self, role: UserRole) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.role == role)
        )
        return result.scalar_one()


class AuditLogRepository(BaseRepository[AuditLog]):
    model = AuditLog

    async def search(
        self, *, query: str | None, limit: int, offset: int
    ) -> tuple[list[tuple[AuditLog, str | None, str | None]], int]:
        """Returns (log, actor_name, actor_email) tuples, newest first."""
        stmt = select(AuditLog, User.full_name, User.email).outerjoin(
            User, AuditLog.actor_id == User.id
        )
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                or_(
                    User.full_name.ilike(like),
                    AuditLog.action.ilike(like),
                    AuditLog.entity_type.ilike(like),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        rows = [(log, actor_name, actor_email) for log, actor_name, actor_email in result.all()]
        return rows, total

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(AuditLog))
        return result.scalar_one()


class PlatformSettingsRepository(BaseRepository[PlatformSettings]):
    model = PlatformSettings

    async def get_singleton(self) -> PlatformSettings:
        settings = await self.session.get(PlatformSettings, 1)
        if settings is None:
            # Seeded by migration per the task brief; construct in-memory defaults as a
            # last resort so this endpoint never 404s in an unseeded environment.
            settings = PlatformSettings(id=1)
            self.session.add(settings)
            await self.session.flush()
        return settings
