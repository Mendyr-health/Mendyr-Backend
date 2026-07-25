"""Bridges Celery's sync task execution with the app's async SQLAlchemy session.

Each Celery worker process runs tasks synchronously, one at a time (with
`worker_prefetch_multiplier=1`), so a fresh event loop per task via `asyncio.run` is safe and
simple — no shared loop/session state needs to survive between tasks.
"""
import asyncio
from collections.abc import Callable, Coroutine
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal

T = TypeVar("T")


def run_with_session(coro_factory: Callable[[AsyncSession], Coroutine[None, None, T]]) -> T:
    async def _runner() -> T:
        async with AsyncSessionLocal() as session:
            result = await coro_factory(session)
            await session.commit()
            return result

    return asyncio.run(_runner())
