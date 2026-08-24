"""Service catalogue — categories/services shown on the app home screen (read-mostly), plus
admin-console CRUD (create/update/toggle-active) used by the Next.js admin portal.
"""

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.service import Service, ServiceCategory
from app.schemas.admin_console import ServiceCreateIn, ServiceUpdateIn


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_categories(self) -> list[ServiceCategory]:
        result = await self.session.execute(
            select(ServiceCategory)
            .where(ServiceCategory.is_active.is_(True))
            .order_by(ServiceCategory.display_order)
        )
        return list(result.scalars().all())

    async def list_services(self, *, category_id: uuid.UUID | None = None) -> list[Service]:
        stmt = select(Service).where(Service.is_active.is_(True)).order_by(Service.display_order)
        if category_id is not None:
            stmt = stmt.where(Service.category_id == category_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_service(self, service_id: uuid.UUID) -> Service:
        service = await self.session.get(Service, service_id)
        if service is None or not service.is_active:
            raise NotFoundError("Service not found.")
        return service

    # ── Admin console: CRUD + search (active and inactive services alike) ──────────────

    async def get_service_any_status(self, service_id: uuid.UUID) -> Service:
        service = await self.session.get(Service, service_id)
        if service is None:
            raise NotFoundError("Service not found.")
        return service

    async def search_services(
        self, *, q: str | None, limit: int, offset: int
    ) -> tuple[list[Service], int]:
        stmt = select(Service)
        count_stmt = select(func.count(Service.id))

        if q:
            like = f"%{q}%"
            search_filter = or_(Service.name.ilike(like), Service.slug.ilike(like))
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Service.name.asc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create_service(self, payload: ServiceCreateIn) -> Service:
        category = await self.session.get(ServiceCategory, payload.category_id)
        if category is None:
            raise NotFoundError("Service category not found.")

        existing = await self.session.execute(select(Service).where(Service.slug == payload.slug))
        if existing.scalar_one_or_none() is not None:
            raise ConflictError("A service with this slug already exists.")

        service = Service(
            category_id=payload.category_id,
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            required_professional_type=payload.required_professional_type,
            duration_minutes=payload.duration_minutes,
            base_price=payload.base_price,
            is_recurring_eligible=payload.is_recurring_eligible,
            requires_prescription=payload.requires_prescription,
            display_order=payload.display_order,
        )
        self.session.add(service)
        await self.session.flush()
        return service

    async def update_service(self, service_id: uuid.UUID, payload: ServiceUpdateIn) -> Service:
        service = await self.get_service_any_status(service_id)

        updates = payload.model_dump(exclude_unset=True, by_alias=False)
        if "category_id" in updates and updates["category_id"] is not None:
            category = await self.session.get(ServiceCategory, updates["category_id"])
            if category is None:
                raise NotFoundError("Service category not found.")
        if "slug" in updates and updates["slug"] != service.slug:
            existing = await self.session.execute(
                select(Service).where(Service.slug == updates["slug"], Service.id != service_id)
            )
            if existing.scalar_one_or_none() is not None:
                raise ConflictError("A service with this slug already exists.")

        for field, value in updates.items():
            setattr(service, field, value)

        await self.session.flush()
        return service

    async def set_service_active(self, service_id: uuid.UUID, *, is_active: bool) -> Service:
        service = await self.get_service_any_status(service_id)
        service.is_active = is_active
        await self.session.flush()
        return service

    async def toggle_service_active(self, service_id: uuid.UUID) -> Service:
        service = await self.get_service_any_status(service_id)
        service.is_active = not service.is_active
        await self.session.flush()
        return service
