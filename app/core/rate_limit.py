"""Rate limiting (slowapi) — protects auth endpoints from abuse.

Backed by Redis in production so limits are shared across every worker process. Falls back to
an in-memory store when REDIS_ENABLED=false — fine for local/dev or a single-process deploy,
but each process then enforces its own separate limit (not shared across replicas/workers).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

_storage_uri = settings.REDIS_URL if settings.REDIS_ENABLED else "memory://"

limiter = Limiter(key_func=get_remote_address, storage_uri=_storage_uri)
