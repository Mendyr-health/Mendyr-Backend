import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ReviewCreateIn(BaseModel):
    booking_id: uuid.UUID
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None
    tags: list[str] | None = None


class ReviewRead(ORMModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    rating: int
    comment: str | None
    tags: list[str] | None
    created_at: datetime
