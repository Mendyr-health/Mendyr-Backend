"""Admin-managed key/value config entries used to drive both UI and backend behavior."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.permissions import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.config import ConfigCreateIn, ConfigRead, ConfigUpdateIn
from app.services.config_service import ConfigService

router = APIRouter(prefix="/configs", tags=["configs"])


@router.get("", response_model=list[ConfigRead])
async def list_configs(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ConfigRead]:
    return await ConfigService(db).list()


@router.get("/{key}", response_model=ConfigRead)
async def get_config(
    key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConfigRead:
    return await ConfigService(db).get_by_key(key)


@router.post("", response_model=ConfigRead, status_code=201)
async def create_config(
    payload: ConfigCreateIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ConfigRead:
    return await ConfigService(db).create(payload)


@router.patch("/{config_id}", response_model=ConfigRead)
async def update_config(
    config_id: uuid.UUID,
    payload: ConfigUpdateIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ConfigRead:
    return await ConfigService(db).update(config_id, payload)


@router.delete("/{config_id}", response_model=MessageResponse)
async def delete_config(
    config_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await ConfigService(db).delete(config_id)
    return MessageResponse(message="Config deleted.")
