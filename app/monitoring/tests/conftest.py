from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

os.environ.setdefault("XLINK_ENV", "testing")
os.environ.setdefault("XLINK_RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("XLINK_JWT_SECRET_KEY", "testing-secret-key-32-chars-minimum-9x")
os.environ.setdefault("XLINK_ARGON2_TIME_COST", "1")
os.environ.setdefault("XLINK_ARGON2_MEMORY_COST", "8192")
os.environ.setdefault("XLINK_ARGON2_PARALLELISM", "1")

from app.core.config import Settings
from app.db.base import Base
from app.db.session import Database


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url_override="sqlite+aiosqlite:///:memory:")


@pytest.fixture
async def db(settings: Settings) -> AsyncIterator[Database]:
    database = Database(settings)
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield database
    finally:
        await database.dispose()
