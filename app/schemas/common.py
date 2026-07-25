"""Shared response envelopes and pagination primitives used across every router."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for schemas hydrated directly from SQLAlchemy ORM instances."""

    model_config = ConfigDict(from_attributes=True)


class GeoPoint(BaseModel):
    latitude: float
    longitude: float


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    has_next: bool


class PaginationParams(BaseModel):
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class MessageResponse(BaseModel):
    message: str
