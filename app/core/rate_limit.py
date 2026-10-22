"""Rate limiting (slowapi) — protects auth endpoints from abuse.

Backed by Redis in production so limits are shared across every worker process. Falls back to
an in-memory store when REDIS_ENABLED=false — fine for local/dev or a single-process deploy,
but each process then enforces its own separate limit (not shared across replicas/workers).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings

_storage_uri = settings.REDIS_URL if settings.REDIS_ENABLED else "memory://"


def client_ip(request: Request) -> str:
    """The caller's IP, used as the rate-limit bucket.

    In production every request arrives through proxies (the web app's Vercel rewrite, then
    FastAPI Cloud's load balancer), so the socket peer is a proxy shared by all users —
    bucketing on it would turn "10/minute" into a global limit. The left-most
    X-Forwarded-For entry is the original client as the outermost proxy saw it. A caller
    hitting the API directly can spoof it, which only lets them dodge their own limit.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip, storage_uri=_storage_uri)
