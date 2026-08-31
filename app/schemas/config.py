import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ConfigCreateIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=150)
    value: Any
    description: str | None = None
    is_active: bool = True


class ConfigUpdateIn(BaseModel):
    """All fields optional — only what's provided gets patched onto the existing row."""

    value: Any = None
    description: str | None = None
    is_active: bool | None = None


class ConfigRead(ORMModel):
    id: uuid.UUID
    key: str
    value: Any
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
