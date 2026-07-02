"""Shared pytest fixtures: isolated in-memory DB and a fresh FastAPI test client per test."""

from __future__ import annotations

import os

# Force in-memory SQLite and dummy API keys before app modules import settings,
# so tests never touch a real DB file or make real network calls accidentally.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")
os.environ.setdefault("APP_ENV", "development")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.database import Base
from app.services import cache


@pytest_asyncio.fixture
async def test_engine():
    """A fresh in-memory SQLite engine per test, shared across connections via StaticPool."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        from app.db import models  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def app_client(test_engine, monkeypatch):
    """Overrides the app's DB engine/session with the test engine, returns an AsyncClient."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app import db as db_module
    from app.db import database as database_module

    test_session_local = async_sessionmaker(
        bind=test_engine, expire_on_commit=False, class_=database_module.AsyncSession
    )
    monkeypatch.setattr(database_module, "engine", test_engine)
    monkeypatch.setattr(database_module, "AsyncSessionLocal", test_session_local)

    cache.clear_cache()
    get_settings.cache_clear()

    from app.main import create_app

    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_lab_report_text() -> str:
    return (
        "Patient: Jane Doe\n"
        "Test: Complete Blood Count\n"
        "Hemoglobin: 10.2 g/dL (Reference: 12.0-15.5 g/dL)\n"
        "WBC Count: 7.2 x10^9/L (Reference: 4.0-11.0 x10^9/L)\n"
        "Platelets: 250 x10^9/L (Reference: 150-450 x10^9/L)\n"
    )
