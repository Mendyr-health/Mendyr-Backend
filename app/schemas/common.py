"""Shared response envelopes and pagination primitives used across every router."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.core.constants import UserRole

T = TypeVar("T")

# The frontend's Role type (src/lib/mock-users.ts) is "SUPER_ADMIN" | "ADMIN" | "NURSE" |
# "PATIENT" — uppercase, and "NURSE" rather than this backend's "professional" (the role
# name predates this product settling on "nurse" as the user-facing term, and changing the
# enum's stored value would mean a data migration for no real benefit). Every schema that
# exposes `role` to the frontend must serialize through this, or role-based routing on the
# frontend (dashboard layout's nav-link switch, onboarding redirect, etc.) silently breaks
# on the case/name mismatch — it did once already; see the git history of this comment.
_FRONTEND_ROLE_NAMES: dict[UserRole, str] = {
    UserRole.PATIENT: "PATIENT",
    UserRole.PROFESSIONAL: "NURSE",
    UserRole.ADMIN: "ADMIN",
    UserRole.SUPER_ADMIN: "SUPER_ADMIN",
    UserRole.OPS: "OPS",
}


def frontend_role_name(role: UserRole) -> str:
    return _FRONTEND_ROLE_NAMES[role]


class ORMModel(BaseModel):
    """Base for schemas hydrated directly from SQLAlchemy ORM instances."""

    model_config = ConfigDict(from_attributes=True)


class CamelModel(BaseModel):
    """Base for schemas facing the Next.js frontend (src/types/index.ts), which is written
    entirely in camelCase — the rest of this backend is snake_case (Python-idiomatic), so
    schemas that speak directly to that frontend opt into this instead of fighting the grain
    of either side. `populate_by_name` accepts snake_case too (handy in tests/internal use);
    FastAPI's `response_model_by_alias=True` default means responses always serialize as
    camelCase, matching what the frontend actually expects.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CamelORMModel(CamelModel):
    """CamelModel + from_attributes, for camelCase schemas hydrated from ORM instances."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


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


class ApiError(BaseModel):
    code: str
    message: str
    details: object | None = None


class PaginationMeta(CamelModel):
    page: int
    limit: int
    total: int
    total_pages: int


class ApiResponse(BaseModel, Generic[T]):
    """The response envelope every `/api/*` route returns — matches the frontend's
    `ApiResponse<T>` type (src/types/index.ts) exactly: `{success, data, meta, error}`.

    Use the `ok()`/`fail()` constructors rather than building this directly, so every
    endpoint produces the same shape without repeating the boilerplate.
    """

    success: bool
    data: T | None = None
    meta: PaginationMeta | None = None
    error: ApiError | None = None

    @classmethod
    def ok(cls, data: T | None = None, *, meta: PaginationMeta | None = None) -> "ApiResponse[T]":
        return cls(success=True, data=data, meta=meta, error=None)

    @classmethod
    def fail(cls, code: str, message: str) -> "ApiResponse[T]":
        return cls(success=False, data=None, meta=None, error=ApiError(code=code, message=message))


def pagination_meta(*, page: int, limit: int, total: int) -> PaginationMeta:
    total_pages = (total + limit - 1) // limit if limit else 0
    return PaginationMeta(page=page, limit=limit, total=total, total_pages=total_pages)
