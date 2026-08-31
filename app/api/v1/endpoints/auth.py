"""Email + password authentication endpoints."""
from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import DevicePlatform
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.schemas.auth import LoginIn, RefreshTokenIn, RegisterIn, TokenPair
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_platform(
    x_client_platform: str | None = Header(default=None),
) -> str:
    """Caller-declared platform (web/ios/android). Defaults to web when unset, since
    unmodified/legacy web clients don't send this header — native clients must send it
    to opt out of the refresh-token cookie (cookies don't work reliably in native/WebView
    contexts, see DevicePlatform)."""
    if x_client_platform is None:
        return DevicePlatform.WEB.value
    return x_client_platform.strip().lower()


def _set_refresh_cookie(response: Response, refresh_token: str, client_platform: str) -> None:
    if not settings.REFRESH_TOKEN_COOKIE_ENABLED:
        return
    if client_platform != DevicePlatform.WEB.value:
        return
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/api/v1/auth",
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
        referral_code=payload.referral_code,
    )
    _set_refresh_cookie(response, tokens.refresh_token, client_platform)
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
    _set_refresh_cookie(response, tokens.refresh_token, client_platform)
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
    _set_refresh_cookie(response, tokens.refresh_token, client_platform)
    return tokens

