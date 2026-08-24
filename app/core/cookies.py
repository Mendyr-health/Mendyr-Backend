"""httpOnly cookie helpers for the email/password web+app session (see app/api/web/auth.py).

The frontend runs three ways — browser, and bundled inside the Capacitor iOS/Android
shells — and in the native shells the page is served from a different origin than this
API, so the auth cookies must be sendable cross-site. That requires `SameSite=None` +
`Secure`, which in turn requires HTTPS — not available for plain-HTTP local dev, so
this falls back to `SameSite=Lax` + non-Secure there instead (same-origin dev only).
"""

from fastapi import Response

from app.core.config import settings

ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"


def _cookie_kwargs() -> dict:
    if settings.is_production:
        return {"secure": True, "samesite": "none"}
    return {"secure": False, "samesite": "lax"}


def set_auth_cookies(response: Response, *, access_token: str, refresh_token: str) -> None:
    common = _cookie_kwargs()
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        access_token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")
