"""Shared pytest fixtures: an isolated async DB session per test + an HTTPX client for the app.

Assumes a Postgres+PostGIS instance is reachable via the same `.env` settings used by the app
(point `POSTGRES_*` at a disposable test database — CI should provision one per run).
"""
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base_class import Base
from app.db.session import AsyncSessionLocal, engine
from app.main import app


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _prepare_schema():
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
