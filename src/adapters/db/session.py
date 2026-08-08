"""Engine and session factory.

The database URL is read once, from `CARDINAL_DATABASE_URL`. When it is unset the
application is expected to fall back to the in-memory catalogue rather than fail --
`DEMO_MODE=true` must always work with the entire environment unset (CONSTITUTION III.7).
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

ENV_DATABASE_URL = "CARDINAL_DATABASE_URL"

DEFAULT_DATABASE_URL = "postgresql+psycopg://cardinal:cardinal@localhost:5432/cardinal"


def database_url() -> str | None:
    """`None` when unset -- callers fall back to the in-memory store."""
    return os.environ.get(ENV_DATABASE_URL) or None


def resolved_database_url() -> str:
    return database_url() or DEFAULT_DATABASE_URL


_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(resolved_database_url(), pool_pre_ping=True, future=True)
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def db_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """`asyncio.run`, but on a loop psycopg can actually use.

    Windows defaults to `ProactorEventLoop`, which psycopg's async mode refuses outright --
    so every entry point that touches the database has to select a loop rather than call
    `asyncio.run` directly. Uses `asyncio.Runner` instead of the event-loop-policy API,
    which is deprecated as of 3.14.
    """
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            return runner.run(coro)
    return asyncio.run(coro)


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
