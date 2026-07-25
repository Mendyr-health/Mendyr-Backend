"""Read-mostly service catalogue — categories and services shown on the app home screen."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.service import Service, ServiceCategory


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
