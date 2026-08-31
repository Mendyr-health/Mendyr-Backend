"""Admin-curated named queries: admins manage the SQL, any authenticated user can run one."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.permissions import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.query_info import (
    QueryInfoCreateIn,
    QueryInfoRead,
    QueryInfoUpdateIn,
    QueryResultPage,
)
from app.services.query_info_service import QueryInfoService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=list[QueryInfoRead])
async def list_query_info(
    current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[QueryInfoRead]:
    return await QueryInfoService(db).list()


@router.post("", response_model=QueryInfoRead, status_code=201)
async def create_query_info(
    payload: QueryInfoCreateIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> QueryInfoRead:
    return await QueryInfoService(db).create(payload)


@router.patch("/{query_info_id}", response_model=QueryInfoRead)
async def update_query_info(
    query_info_id: uuid.UUID,
    payload: QueryInfoUpdateIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> QueryInfoRead:
    return await QueryInfoService(db).update(query_info_id, payload)


@router.delete("/{query_info_id}", response_model=MessageResponse)
async def delete_query_info(
    query_info_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await QueryInfoService(db).delete(query_info_id)
    return MessageResponse(message="Query deleted.")


@router.get("/{name}/data", response_model=QueryResultPage)
async def run_query_info(
    name: str,
    page: int = 1,
    page_size: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueryResultPage:
    return await QueryInfoService(db).run(name, page=page, page_size=page_size)
