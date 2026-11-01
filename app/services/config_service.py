"""Admin-managed key/value config entries used to drive both UI and backend behavior.

Registered keys (see `app.core.config_registry`) are validated on write and resolved against
their defaults on read. Reads go through a short per-process cache: pricing and booking rules
are consulted on hot paths, and a config change taking a few seconds to reach every worker is
fine.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config_registry import REGISTRY, Banner, BannersConfig, validate_value
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models.config import Config
from app.repositories.config_repo import ConfigRepository
from app.schemas.config import ConfigCreateIn, ConfigUpdateIn
from app.services.audit_service import AuditService

logger = get_logger(__name__)

M = TypeVar("M", bound=BaseModel)

CACHE_TTL_SECONDS = 15
_cache: dict[str, object] = {}
_cache_loaded_at = 0.0


def invalidate_config_cache() -> None:
    global _cache_loaded_at
    _cache_loaded_at = 0.0


def _validated(key: str, value: object) -> object:
    try:
        return validate_value(key, value)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or key
        raise ValidationAppError(f"Invalid value for '{key}' at {where}: {first['msg']}") from exc


def _banner_visible(banner: Banner, *, role: str | None, platform: str | None) -> bool:
    now = datetime.now(UTC)
    if not banner.enabled:
        return False
    if banner.starts_at and banner.starts_at.replace(tzinfo=banner.starts_at.tzinfo or UTC) > now:
        return False
    if banner.ends_at and banner.ends_at.replace(tzinfo=banner.ends_at.tzinfo or UTC) < now:
        return False
    if role and role not in banner.roles:
        return False
    return not (platform and platform not in banner.platforms)


class ConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.configs = ConfigRepository(session)
        self.audit = AuditService(session)

    # ── Typed reads ─────────────────────────────────────────────────────

    async def _active_values(self) -> dict[str, object]:
        global _cache, _cache_loaded_at
        if time.monotonic() - _cache_loaded_at > CACHE_TTL_SECONDS:
            rows = await self.configs.list_all()
            _cache = {row.key: row.value for row in rows if row.is_active}
            _cache_loaded_at = time.monotonic()
        return _cache

    async def typed(self, key: str, model: type[M]) -> M:
        """The active value for a registered key, or its default when there's no active row
        (or the stored value predates a schema change and no longer validates)."""
        raw = (await self._active_values()).get(key)
        if raw is not None:
            try:
                return model.model_validate(raw)
            except ValidationError:
                logger.warning("config.invalid_stored_value", key=key)
        return model()

    async def app_bundle(
        self, *, role: str | None = None, platform: str | None = None
    ) -> dict[str, object]:
        """Everything the apps read, resolved: each public registered key (default merged
        with the admin's value), plus any free-form active `app.*` key. Banners are filtered
        to the ones this role/platform should see right now. `version` changes whenever any
        value does, so a client can skip re-rendering an unchanged bundle."""
        values: dict[str, object] = {}
        for key, spec in REGISTRY.items():
            if spec.public:
                values[key] = (await self.typed(key, spec.model)).model_dump(mode="json")
        for key, value in (await self._active_values()).items():
            if key.startswith("app.") and key not in REGISTRY:
                values[key] = value

        banners = BannersConfig.model_validate(values["app.banners"])
        values["app.banners"] = {
            "items": [
                b.model_dump(mode="json")
                for b in banners.items
                if _banner_visible(b, role=role, platform=platform)
            ]
        }
        digest = hashlib.sha256(
            json.dumps(values, sort_keys=True, default=str).encode()
        ).hexdigest()[:12]
        return {"version": digest, "configs": values}

    # ── Admin CRUD ──────────────────────────────────────────────────────

    async def list(self) -> list[Config]:
        return await self.configs.list_all()

    async def get_by_key(self, key: str) -> Config:
        config = await self.configs.get_by_key(key)
        if config is None:
            raise NotFoundError(f"No config found for key '{key}'.")
        return config

    async def registry(self) -> list[dict[str, object]]:
        """Every registered key with its schema, default and stored row — what the portal
        needs to render a typed editor."""
        rows = {row.key: row for row in await self.configs.list_all()}
        out = []
        for key, spec in REGISTRY.items():
            row = rows.get(key)
            out.append(
                {
                    "key": key,
                    "label": spec.label,
                    "group": spec.group,
                    "description": spec.description,
                    "public": spec.public,
                    "schema": spec.model.model_json_schema(),
                    "default": spec.model().model_dump(mode="json"),
                    "value": (await self.typed(key, spec.model)).model_dump(mode="json"),
                    "is_overridden": row is not None and row.is_active,
                    "updated_at": row.updated_at if row else None,
                    "id": row.id if row else None,
                }
            )
        return out

    async def create(self, payload: ConfigCreateIn, *, actor_id: uuid.UUID | None = None) -> Config:
        if await self.configs.get_by_key(payload.key) is not None:
            raise ConflictError(f"A config with key '{payload.key}' already exists.")

        config = Config(
            key=payload.key,
            value=_validated(payload.key, payload.value),
            description=payload.description,
            is_active=payload.is_active,
        )
        self.configs.add(config)
        await self.session.flush()
        self._audit(actor_id, "config.create", config.key, {"value": config.value})
        return config

    async def upsert(
        self, key: str, value: object, *, actor_id: uuid.UUID | None, description: str | None
    ) -> Config:
        """Set a key's value, creating the row on first save — the portal's typed editors
        save by key, not by row id."""
        normalised = _validated(key, value)
        config = await self.configs.get_by_key(key)
        before = config.value if config else None
        if config is None:
            spec = REGISTRY.get(key)
            config = Config(
                key=key,
                value=normalised,
                description=description or (spec.description if spec else None),
                is_active=True,
            )
            self.configs.add(config)
        else:
            config.value = normalised
            config.is_active = True
            if description is not None:
                config.description = description
        await self.session.flush()
        self._audit(actor_id, "config.update", key, {"before": before, "after": normalised})
        return config

    async def update(
        self, config_id: uuid.UUID, payload: ConfigUpdateIn, *, actor_id: uuid.UUID | None = None
    ) -> Config:
        config = await self.configs.get(config_id)
        if config is None:
            raise NotFoundError("Config not found.")

        changes = payload.model_dump(exclude_unset=True)
        if "value" in changes:
            if changes["value"] is None:
                raise ValidationAppError("value can't be null — delete the config instead.")
            changes["value"] = _validated(config.key, changes["value"])
        before = config.value
        for field, value in changes.items():
            if value is None and field == "is_active":
                continue
            setattr(config, field, value)

        await self.session.flush()
        self._audit(
            actor_id, "config.update", config.key, {"before": before, "after": config.value}
        )
        return config

    async def toggle_active(
        self, config_id: uuid.UUID, *, actor_id: uuid.UUID | None = None
    ) -> Config:
        config = await self.configs.get(config_id)
        if config is None:
            raise NotFoundError("Config not found.")
        config.is_active = not config.is_active
        await self.session.flush()
        self._audit(actor_id, "config.toggle", config.key, {"is_active": config.is_active})
        return config

    async def get_active_dict(self) -> dict[str, object]:
        configs = await self.configs.list_all()
        return {c.key: c.value for c in configs if c.is_active}

    async def summary(self) -> dict[str, object]:
        configs = await self.configs.list_all()
        total = len(configs)
        active = sum(1 for c in configs if c.is_active)
        categories: dict[str, int] = {}
        for c in configs:
            domain = c.key.split(".")[0] if "." in c.key else "general"
            categories[domain] = categories.get(domain, 0) + 1
        return {
            "total_configs": total,
            "active_configs": active,
            "inactive_configs": total - active,
            "categories": categories,
        }

    async def delete(self, config_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> None:
        config = await self.configs.get(config_id)
        if config is None:
            raise NotFoundError("Config not found.")
        self._audit(actor_id, "config.delete", config.key, {"value": config.value})
        await self.configs.delete(config)
        await self.session.flush()

    def _audit(self, actor_id: uuid.UUID | None, action: str, key: str, metadata: dict) -> None:
        invalidate_config_cache()
        self.audit.log(
            actor_id=actor_id, action=action, entity_type="config", entity_id=key, metadata=metadata
        )
