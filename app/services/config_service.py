"""Admin-managed key/value config entries used to drive both UI and backend behavior."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.config import Config
from app.repositories.config_repo import ConfigRepository
from app.schemas.config import ConfigCreateIn, ConfigUpdateIn


class ConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.configs = ConfigRepository(session)

    async def list(self) -> list[Config]:
        return await self.configs.list_all()

    async def get_by_key(self, key: str) -> Config:
        config = await self.configs.get_by_key(key)
        if config is None:
            raise NotFoundError(f"No config found for key '{key}'.")
        return config

    async def create(self, payload: ConfigCreateIn) -> Config:
        if await self.configs.get_by_key(payload.key) is not None:
            raise ConflictError(f"A config with key '{payload.key}' already exists.")

        config = Config(
            key=payload.key,
            value=payload.value,
            description=payload.description,
            is_active=payload.is_active,
        )
        self.configs.add(config)
        await self.session.flush()
        return config

    async def update(self, config_id: uuid.UUID, payload: ConfigUpdateIn) -> Config:
        config = await self.configs.get(config_id)
        if config is None:
            raise NotFoundError("Config not found.")

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(config, field, value)

        await self.session.flush()
        return config

    async def toggle_active(self, config_id: uuid.UUID) -> Config:
        config = await self.configs.get(config_id)
        if config is None:
            raise NotFoundError("Config not found.")
        config.is_active = not config.is_active
        await self.session.flush()
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

    async def delete(self, config_id: uuid.UUID) -> None:
        config = await self.configs.get(config_id)
        if config is None:
            raise NotFoundError("Config not found.")
        await self.configs.delete(config)
        await self.session.flush()
