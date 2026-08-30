"""Email + password authentication endpoints."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.schemas.auth import LoginIn, RefreshTokenIn, RegisterIn, TokenPair
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPair, status_code=201)
@limiter.limit("10/minute")
async def register(
    request: Request, payload: RegisterIn, db: AsyncSession = Depends(get_db)
) -> TokenPair:
    return await AuthService(db).register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
        phone_number=payload.phone_number,
        gender=payload.gender,
        referral_code=payload.referral_code,
    )


@router.post("/login", response_model=TokenPair)
@limiter.limit("10/minute")
async def login(
    request: Request, payload: LoginIn, db: AsyncSession = Depends(get_db)
) -> TokenPair:
    return await AuthService(db).login(email=payload.email, password=payload.password)


@router.post("/token/refresh", response_model=TokenPair)
@limiter.limit("30/minute")
async def refresh_token(
    request: Request, payload: RefreshTokenIn, db: AsyncSession = Depends(get_db)
) -> TokenPair:
    return await AuthService(db).refresh(payload.refresh_token)

