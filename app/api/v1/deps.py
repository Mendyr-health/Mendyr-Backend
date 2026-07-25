"""Shared FastAPI dependencies: DB session passthrough, current-user resolution, pagination."""
import uuid

import jwt
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import PaginationParams

DbSession = AsyncSession  # readability alias for route signatures


async def get_current_user(
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header.")

    token = authorization.removeprefix("Bearer ").strip()
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


def pagination_params(page: int = 1, page_size: int = 20) -> PaginationParams:
    return PaginationParams(page=max(page, 1), page_size=min(max(page_size, 1), 100))
