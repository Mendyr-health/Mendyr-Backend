"""Generic cross-entity search used by every admin-console list screen — one endpoint,
dispatched by `entity`, instead of five near-identical list endpoints. See
src/features/admin/useNurses.ts, usePatients.ts, useServices.ts, useWaitlist.ts,
useContacts.ts — all five hit this exact path with a different `entity` value.

Deliberately NOT nested under /admin: the frontend calls it as a bare /api/v1/search.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.admin_console import SearchEntity, SearchResultItem
from app.schemas.common import ApiResponse, pagination_meta
from app.services.admin_console_service import AdminConsoleService

router = APIRouter(tags=["search"])


@router.get("/search", response_model=ApiResponse[list[SearchResultItem]])
async def search(
    entity: SearchEntity,
    q: str | None = None,
    status: str | None = None,
    page: int = 1,
    limit: int = 20,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[SearchResultItem]]:
    items, total = await AdminConsoleService(db).search(
        entity=entity, q=q, status=status, limit=limit, offset=(page - 1) * limit
    )
    return ApiResponse.ok(items, meta=pagination_meta(page=page, limit=limit, total=total))
