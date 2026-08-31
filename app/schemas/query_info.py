import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class QueryInfoCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    query: str = Field(..., min_length=1)
    batch_size: int = Field(50, ge=1, le=500)
    is_active: bool = True


class QueryInfoUpdateIn(BaseModel):
    query: str | None = Field(None, min_length=1)
    batch_size: int | None = Field(None, ge=1, le=500)
    is_active: bool | None = None


class QueryInfoRead(ORMModel):
    id: uuid.UUID
    name: str
    query: str
    batch_size: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class QueryResultPage(BaseModel):
    items: list[dict[str, Any]]
    page: int
    page_size: int
    has_next: bool
