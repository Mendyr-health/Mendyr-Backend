"""Shared FastAPI dependencies: DB session passthrough, current-user resolution, pagination."""
import uuid

import jwt
from fastapi import Cookie, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import UserRole
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.professional import ProfessionalProfile
from app.models.user import User
from app.repositories.professional_repo import ProfessionalRepository
from app.schemas.common import PaginationParams

DbSession = AsyncSession  # readability alias for route signatures


async def get_current_user(
    authorization: str = Header(default=""),
    # Cookie-based fallback for the Next.js frontend, which authenticates purely via the
    # httponly cookie `_set_access_cookie` sets on login/register/refresh and never sends an
    # Authorization header. Bearer still takes priority for native/API/Postman clients.
    access_token_cookie: str | None = Cookie(default=None, alias=settings.ACCESS_TOKEN_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> User:
    if authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    elif access_token_cookie:
        token = access_token_cookie
    else:
        raise UnauthorizedError("Missing or malformed Authorization header.")

    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid access token.") from exc

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type.")

    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise UnauthorizedError("User no longer exists.")
    return user


async def get_optional_current_user(
    authorization: str = Header(default=""),
    access_token_cookie: str | None = Cookie(default=None, alias=settings.ACCESS_TOKEN_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """`get_current_user`, but None instead of 401 — for endpoints that must work with an
    expired or missing session (logout has to clear cookies either way)."""
    try:
        return await get_current_user(authorization, access_token_cookie, db)
    except UnauthorizedError:
        return None


async def get_current_professional(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ProfessionalProfile:
    """The calling professional's profile; 404 until they've completed onboarding.

    Checks the role inline rather than via `permissions.require_professional`: that module
    imports this one while it's still initializing, so importing it back here is a cycle."""
    if current_user.role != UserRole.PROFESSIONAL:
        raise ForbiddenError("Requires one of roles: ['professional']")
    profile = await ProfessionalRepository(db).get_by_user_id(current_user.id)
    if profile is None:
        raise NotFoundError("Complete your professional profile first.")
    return profile


def pagination_params(page: int = 1, page_size: int = 20) -> PaginationParams:
    return PaginationParams(page=max(page, 1), page_size=min(max(page_size, 1), 100))
