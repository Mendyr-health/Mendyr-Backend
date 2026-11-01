"""Service catalogue — categories and services shown on the app home screen, and their
admin editing.

Presentation content (image, highlights, FAQs) lives in the `catalog.content` config rather
than the catalogue tables; reads merge it in, writes split it out.
"""

import re
import uuid

from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config_registry import CatalogContent, ServiceContent
from app.core.constants import BookingStatus
from app.core.exceptions import ConflictError, NotFoundError
from app.models.booking import Booking
from app.models.review import Review
from app.models.service import Service, ServiceCategory
from app.schemas.service import (
    CategoryWriteIn,
    ServiceAdminRead,
    ServiceRead,
    ServiceWriteIn,
)
from app.services.audit_service import AuditService
from app.services.config_service import ConfigService

CONTENT_FIELDS = ("image_url", "tagline", "badge", "includes", "excludes", "faqs")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:140] or "item"


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.config = ConfigService(session)

    async def list_categories(self, *, include_inactive: bool = False) -> list[ServiceCategory]:
        stmt = select(ServiceCategory).order_by(ServiceCategory.display_order)
        if not include_inactive:
            stmt = stmt.where(ServiceCategory.is_active.is_(True))
        return list((await self.session.execute(stmt)).scalars().all())

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

    # ── Enriched reads ──────────────────────────────────────────────────

    async def _stats(self, service_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple]:
        """(rating_avg, rating_count, completed bookings) per service, in two queries."""
        if not service_ids:
            return {}
        ratings = await self.session.execute(
            select(Booking.service_id, func.avg(Review.rating), func.count(Review.id))
            .join(Review, Review.booking_id == Booking.id)
            .where(Booking.service_id.in_(service_ids))
            .group_by(Booking.service_id)
        )
        booked = await self.session.execute(
            select(Booking.service_id, func.count(Booking.id))
            .where(
                Booking.service_id.in_(service_ids),
                Booking.status == BookingStatus.COMPLETED,
            )
            .group_by(Booking.service_id)
        )
        counts = dict(booked.all())
        rating_rows = {sid: (avg, n) for sid, avg, n in ratings.all()}
        return {
            sid: (
                round(float(rating_rows[sid][0]), 1) if sid in rating_rows else None,
                rating_rows.get(sid, (None, 0))[1],
                counts.get(sid, 0),
            )
            for sid in service_ids
        }

    async def _enrich(self, services: list[Service], read_model: type[ServiceRead]) -> list:
        content = (await self.config.typed("catalog.content", CatalogContent)).services
        stats = await self._stats([s.id for s in services])
        out = []
        for service in services:
            read = read_model.model_validate(service)
            extra = content.get(str(service.id))
            if extra is not None:
                for field in CONTENT_FIELDS:
                    setattr(read, field, getattr(extra, field))
            read.rating_avg, read.rating_count, read.bookings_count = stats[service.id]
            out.append(read)
        return out

    async def list_service_reads(self, *, category_id: uuid.UUID | None = None) -> list:
        return await self._enrich(await self.list_services(category_id=category_id), ServiceRead)

    async def get_service_read(self, service_id: uuid.UUID) -> ServiceRead:
        return (await self._enrich([await self.get_service(service_id)], ServiceRead))[0]

    # ── Admin ───────────────────────────────────────────────────────────

    async def admin_list_services(self) -> list[ServiceAdminRead]:
        result = await self.session.execute(
            select(Service).order_by(Service.display_order, Service.name)
        )
        return await self._enrich(list(result.scalars().all()), ServiceAdminRead)

    async def _unique_slug(self, model: type, name: str, *, exclude_id: uuid.UUID | None) -> str:
        base = slugify(name)
        slug, n = base, 1
        while True:
            stmt = select(model.id).where(model.slug == slug)
            if exclude_id is not None:
                stmt = stmt.where(model.id != exclude_id)
            if (await self.session.execute(stmt)).first() is None:
                return slug
            n += 1
            slug = f"{base}-{n}"

    async def save_category(
        self, payload: CategoryWriteIn, *, category_id: uuid.UUID | None, actor_id: uuid.UUID
    ) -> ServiceCategory:
        clash = await self.session.execute(
            select(ServiceCategory.id).where(
                func.lower(ServiceCategory.name) == payload.name.lower(),
                ServiceCategory.id != category_id if category_id else true(),
            )
        )
        if clash.first() is not None:
            raise ConflictError("A category with this name already exists.")
        if category_id is None:
            category = ServiceCategory(slug="")
            self.session.add(category)
        else:
            category = await self.session.get(ServiceCategory, category_id)
            if category is None:
                raise NotFoundError("Category not found.")
        for field, value in payload.model_dump().items():
            setattr(category, field, value)
        category.slug = await self._unique_slug(
            ServiceCategory, payload.name, exclude_id=category_id
        )
        await self.session.flush()
        AuditService(self.session).log(
            actor_id=actor_id,
            action="catalog.category.save",
            entity_type="category",
            entity_id=str(category.id),
            metadata=payload.model_dump(mode="json"),
        )
        return category

    async def save_service(
        self, payload: ServiceWriteIn, *, service_id: uuid.UUID | None, actor_id: uuid.UUID
    ) -> ServiceAdminRead:
        if await self.session.get(ServiceCategory, payload.category_id) is None:
            raise NotFoundError("Category not found.")
        if service_id is None:
            service = Service(slug="")
            self.session.add(service)
        else:
            service = await self.session.get(Service, service_id)
            if service is None:
                raise NotFoundError("Service not found.")
        for field, value in payload.model_dump(exclude=set(CONTENT_FIELDS)).items():
            setattr(service, field, value)
        service.slug = await self._unique_slug(Service, payload.name, exclude_id=service_id)
        await self.session.flush()

        catalog = await self.config.typed("catalog.content", CatalogContent)
        catalog.services[str(service.id)] = ServiceContent(
            **payload.model_dump(include=set(CONTENT_FIELDS))
        )
        await self.config.upsert(
            "catalog.content",
            catalog.model_dump(mode="json"),
            actor_id=actor_id,
            description=None,
        )
        AuditService(self.session).log(
            actor_id=actor_id,
            action="catalog.service.save",
            entity_type="service",
            entity_id=str(service.id),
            metadata=payload.model_dump(mode="json"),
        )
        return (await self._enrich([service], ServiceAdminRead))[0]
