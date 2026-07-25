"""OTP-first authentication endpoints."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.schemas.auth import OTPRequestIn, OTPVerifyIn, RefreshTokenIn, TokenPair
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request", response_model=MessageResponse)
@limiter.limit("5/minute")
async def request_otp(
    request: Request, payload: OTPRequestIn, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    await AuthService(db).request_otp(payload.phone_number, payload.purpose)
    return MessageResponse(message="OTP sent.")


@router.post("/otp/verify", response_model=TokenPair)
@limiter.limit("10/minute")
async def verify_otp(
    request: Request, payload: OTPVerifyIn, db: AsyncSession = Depends(get_db)
) -> TokenPair:
    return await AuthService(db).verify_otp_and_authenticate(
        phone_number=payload.phone_number,
        code=payload.code,
        purpose=payload.purpose,
        full_name=payload.full_name,
        role=payload.role,
        referral_code=payload.referral_code,
    )


@router.post("/token/refresh", response_model=TokenPair)
async def refresh_token(payload: RefreshTokenIn, db: AsyncSession = Depends(get_db)) -> TokenPair:
    return await AuthService(db).refresh(payload.refresh_token)
