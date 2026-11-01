"""Public, read-only service catalogue shown on the app home screen."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.service import ServiceCategoryRead, ServiceRead
from app.services.catalog_service import CatalogService

router = APIRouter(prefix="/services", tags=["catalog"])


@router.get("/categories", response_model=list[ServiceCategoryRead])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list:
    return await CatalogService(db).list_categories()


@router.get("", response_model=list[ServiceRead])
async def list_services(
    category_id: uuid.UUID | None = Query(default=None), db: AsyncSession = Depends(get_db)
) -> list:
    """Active services with their images, highlights, rating and completed-visit count."""
    return await CatalogService(db).list_service_reads(category_id=category_id)


@router.get("/{service_id}", response_model=ServiceRead)
async def get_service(service_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ServiceRead:
    return await CatalogService(db).get_service_read(service_id)
