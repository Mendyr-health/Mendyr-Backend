"""Email + password authentication endpoints.

Mounted twice by `app.main` — at `/api/v1/auth` (the versioned API, used by native/API
clients with a Bearer token) and again at the bare `/api/auth` (matching the exact paths
`apps/patient/src/hooks/use-auth.ts` and the login/register pages call, which the cookie-only
frontend relies on instead of ever reading a token from the response body).
"""

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.constants import DevicePlatform
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginIn, RefreshTokenIn, RegisterIn, TokenPair
from app.schemas.common import MessageResponse
from app.schemas.user import UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_platform(
    x_client_platform: str | None = Header(default=None),
) -> str:
    """Caller-declared platform (web/ios/android). Defaults to web when unset, since
    unmodified/legacy web clients don't send this header — native clients must send it
    to opt out of the session cookies (cookies don't work reliably in native/WebView
    contexts, see DevicePlatform)."""
    if x_client_platform is None:
        return DevicePlatform.WEB.value
    return x_client_platform.strip().lower()


def _set_session_cookies(response: Response, tokens: TokenPair, client_platform: str) -> None:
    if not settings.REFRESH_TOKEN_COOKIE_ENABLED or client_platform != DevicePlatform.WEB.value:
        return
    # "/api" (not "/api/v1/auth") so the same cookie reaches both mount points this router is
    # registered under, and so the access-token cookie reaches every protected route, not just
    # the auth ones.
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=tokens.refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/api",
    )
    response.set_cookie(
        key=settings.ACCESS_TOKEN_COOKIE_NAME,
        value=tokens.access_token,
        max_age=tokens.expires_in,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/api",
    )


def _clear_session_cookies(response: Response) -> None:
    # `secure`/`samesite` have to mirror `_set_session_cookies` — a browser only treats this as
    # the same cookie when those attributes match, so a `SameSite=None; Secure` session cookie
    # is not actually removed by a bare `lax`/insecure delete, and logout silently leaves the
    # session alive.
    for name in (settings.REFRESH_TOKEN_COOKIE_NAME, settings.ACCESS_TOKEN_COOKIE_NAME):
        response.delete_cookie(
            key=name,
            path="/api",
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite=settings.SESSION_COOKIE_SAMESITE,
        )


@router.post("/register", response_model=TokenPair, status_code=201)
@limiter.limit("10/minute")
async def register(
    request: Request,
    response: Response,
    payload: RegisterIn,
    db: AsyncSession = Depends(get_db),
    client_platform: str = Depends(_client_platform),
) -> TokenPair:
    tokens = await AuthService(db).register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
        phone_number=payload.phone_number,
        gender=payload.gender,
        date_of_birth=payload.date_of_birth,
        extended_attributes=payload.extended_attributes,
        referral_code=payload.referral_code,
    )
    _set_session_cookies(response, tokens, client_platform)
    return tokens


@router.post("/login", response_model=TokenPair)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    payload: LoginIn,
    db: AsyncSession = Depends(get_db),
    client_platform: str = Depends(_client_platform),
) -> TokenPair:
    tokens = await AuthService(db).login(email=payload.email, password=payload.password)
    _set_session_cookies(response, tokens, client_platform)
    return tokens


@router.post("/token/refresh", response_model=TokenPair)
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    response: Response,
    payload: RefreshTokenIn,
    db: AsyncSession = Depends(get_db),
    client_platform: str = Depends(_client_platform),
) -> TokenPair:
    tokens = await AuthService(db).refresh(payload.refresh_token)
    _set_session_cookies(response, tokens, client_platform)
    return tokens


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    """Cookie-resolvable "who am I" — what `GET /api/auth/me` in `use-auth.ts` expects.
    Equivalent to `GET /users/me`, kept here too since the frontend calls this exact path."""
    return current_user


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Revokes every refresh token for the caller (not just the current session's) and clears
    both session cookies. There is no per-session revoke (see `RefreshTokenRepository`), so
    this logs the user out everywhere, not just this device — acceptable for a prototype."""
    await AuthService(db).logout(current_user.id)
    _clear_session_cookies(response)
    return MessageResponse(message="Logged out.")
