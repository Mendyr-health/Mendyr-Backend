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
    return await CatalogService(db).list_services(category_id=category_id)
