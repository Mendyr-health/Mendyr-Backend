"""Shared pytest fixtures: an isolated async DB session per test + an HTTPX client for the app.

Assumes a Postgres+PostGIS instance is reachable via the same `.env` settings used by the app
(point `POSTGRES_*` at a disposable test database — CI should provision one per run).
"""
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base_class import Base
from app.db.session import AsyncSessionLocal, engine
from app.main import app

_LOCAL_HOST_MARKERS = ("localhost", "127.0.0.1", "::1")


def _refuse_unless_local_database() -> None:
    """`create_all`/`drop_all` below is destructive — it has already wiped a real Supabase
    project once by running against whatever `.env` happened to point at. Any remote host
    (Supabase, RDS, etc.) is by definition not a disposable throwaway database, so refuse to
    run against anything that isn't obviously local rather than trust a docstring warning."""
    host = settings.POSTGRES_HOST.lower()
    if not any(marker in host for marker in _LOCAL_HOST_MARKERS):
        raise RuntimeError(
            f"Refusing to run the test suite against POSTGRES_HOST={settings.POSTGRES_HOST!r} — "
            "this fixture drops every table when the session ends. Point POSTGRES_* at a "
            "local/disposable database (localhost/127.0.0.1) before running tests, e.g. a "
            "separate .env.test, not your Supabase/production .env."
        )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _prepare_schema():
    _refuse_unless_local_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
