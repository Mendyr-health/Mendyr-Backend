"""Email/password auth for the Next.js frontend — mounted at /api/auth/* directly by
app.main (not under /api/v1), matching exactly what the frontend calls
(src/hooks/use-auth.ts, src/app/(auth)/login and register pages).
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.security import create_access_token, create_refresh_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth_web import AuthResultOut, LoginIn, RegisterIn, UserPublicOut
from app.schemas.common import ApiResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth-web"])


def _issue_session_cookies(response: Response, user: User) -> None:
    set_auth_cookies(
        response,
        access_token=create_access_token(str(user.id), role=user.role.value),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/login", response_model=ApiResponse[AuthResultOut])
async def login(
    payload: LoginIn, response: Response, db: AsyncSession = Depends(get_db)
) -> ApiResponse[AuthResultOut]:
    user = await AuthService(db).login_with_password(payload.email, payload.password)
    _issue_session_cookies(response, user)
    return ApiResponse.ok(AuthResultOut(user=UserPublicOut.model_validate(user)))


@router.post("/register", response_model=ApiResponse[AuthResultOut])
async def register(
    payload: RegisterIn, response: Response, db: AsyncSession = Depends(get_db)
) -> ApiResponse[AuthResultOut]:
    user = await AuthService(db).register(payload)
    _issue_session_cookies(response, user)
    return ApiResponse.ok(AuthResultOut(user=UserPublicOut.model_validate(user)))


@router.get("/me", response_model=ApiResponse[UserPublicOut])
async def me(current_user: User = Depends(get_current_user)) -> ApiResponse[UserPublicOut]:
    return ApiResponse.ok(UserPublicOut.model_validate(current_user))


@router.post("/logout", response_model=ApiResponse[None])
async def logout(response: Response) -> ApiResponse[None]:
    clear_auth_cookies(response)
    return ApiResponse.ok(None)
