"""Admin-managed key/value config entries used to drive both UI and backend behavior.

The apps read `GET /configs/app` (public); everything else is admin-only. Static paths are
declared before `/{key}` so they aren't swallowed by it.
"""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.config import ConfigCreateIn, ConfigRead, ConfigUpdateIn
from app.services.config_service import ConfigService

router = APIRouter(prefix="/configs", tags=["configs"])


class ConfigUpsertIn(BaseModel):
    value: Any
    description: str | None = None


@router.get("/app", response_model=dict[str, object])
async def get_app_bundle(
    role: Literal["patient", "professional"] | None = Query(default=None),
    platform: Literal["android", "ios", "web"] | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """The resolved config bundle the apps run on: feature flags, theme, home layout,
    banners, copy, support numbers, booking rules, version gates. Public — the apps need it
    before login (maintenance screen, onboarding slides). Returns `{version, configs}`."""
    return await ConfigService(db).app_bundle(role=role, platform=platform)


@router.get("/app/active", response_model=dict[str, object])
async def get_active_app_configs(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    """Raw active configs as a flat dictionary. Kept for older clients — prefer
    `GET /configs/app`, which fills in defaults and hides backend-only keys."""
    bundle = await ConfigService(db).app_bundle()
    return bundle["configs"]  # type: ignore[return-value]


@router.get("/registry", response_model=list[dict[str, object]])
async def get_config_registry(
    current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[dict[str, object]]:
    """Every typed config key with its JSON schema, default and current value."""
    return await ConfigService(db).registry()


@router.get("/summary", response_model=dict[str, object])
async def get_configs_summary(
    current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, object]:
    return await ConfigService(db).summary()


@router.put("/by-key/{key}", response_model=ConfigRead)
async def upsert_config_by_key(
    key: str,
    payload: ConfigUpsertIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ConfigRead:
    """Save a key's value (validated against its schema), creating the row if needed."""
    return await ConfigService(db).upsert(
        key, payload.value, actor_id=current_user.id, description=payload.description
    )


@router.get("", response_model=list[ConfigRead])
async def list_configs(
    current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[ConfigRead]:
    return await ConfigService(db).list()


@router.get("/{key}", response_model=ConfigRead)
async def get_config(
    key: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ConfigRead:
    return await ConfigService(db).get_by_key(key)


@router.post("", response_model=ConfigRead, status_code=201)
async def create_config(
    payload: ConfigCreateIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ConfigRead:
    return await ConfigService(db).create(payload, actor_id=current_user.id)


@router.patch("/{config_id}", response_model=ConfigRead)
async def update_config(
    config_id: uuid.UUID,
    payload: ConfigUpdateIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ConfigRead:
    return await ConfigService(db).update(config_id, payload, actor_id=current_user.id)


@router.patch("/{config_id}/toggle", response_model=ConfigRead)
async def toggle_config(
    config_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ConfigRead:
    """Quick 1-click active/inactive toggle for PBM tools."""
    return await ConfigService(db).toggle_active(config_id, actor_id=current_user.id)


@router.delete("/{config_id}", response_model=MessageResponse)
async def delete_config(
    config_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Deleting a registered key resets it to its default."""
    await ConfigService(db).delete(config_id, actor_id=current_user.id)
    return MessageResponse(message="Config deleted.")
