"""Append-only trail of admin actions — who approved a professional, changed a config,
suspended a user. Read back in the portal's activity views."""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def log(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: str,
        metadata: dict | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                actor_id=actor_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata_json=json.dumps(metadata, default=str) if metadata else None,
                created_at=datetime.now(UTC),
            )
        )

    async def list(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        result = await self.session.execute(stmt.limit(limit).offset(offset))
        return list(result.scalars().all())
