"""Async SQLAlchemy engine/session factory + the `get_db` FastAPI dependency."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_connect_args: dict = {}
if settings.POSTGRES_SSL_REQUIRED:
    _connect_args["ssl"] = "require"
if settings.DB_DISABLE_PREPARED_STATEMENT_CACHE:
    # asyncpg caches prepared statements by name; a transaction-mode PgBouncer pooler hands
    # each query to a different backend connection, so a cached statement name from one
    # backend is meaningless (or colliding) on the next — disabling the cache avoids
    # "prepared statement ... already exists" / "does not exist" errors under that pooler.
    _connect_args["statement_cache_size"] = 0

engine: AsyncEngine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped session. Commits on clean exit, rolls back on exception."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
