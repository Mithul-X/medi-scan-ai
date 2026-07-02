"""
Async SQLite setup via SQLAlchemy + aiosqlite.

SQLite is a deliberate choice here: it's a single file on Render's disk,
zero external service, zero monthly cost, and entirely sufficient for the
"last 3 sessions / last 3 analyses" persistence scope this project needs.

Note: Render's free tier disk is ephemeral across deploys (not across
restarts within the same deploy), so this is fine for a demo/capstone but
documented clearly in the README as a known limitation, not hidden.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create tables if they don't exist. Called once at app startup."""
    # Import models here (not at module top) so they register with Base
    # before create_all runs, without creating a circular import at import time.
    from app.db import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    await engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session, closes it after the request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Context-manager variant for use outside request handlers (services, scripts)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
