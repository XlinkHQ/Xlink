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

# Register every ORM model on Base.metadata so create_all builds the full
# schema (config_sync reads certificates / routing_rules / outbounds, etc.).
import app.domain.certificate
import app.domain.outbound
import app.domain.routing_rule  # noqa: F401
from app.core.config import Settings
from app.core.lifespan import AppState
from app.db.base import Base
from app.db.redis import RedisCache
from app.db.session import Database
from app.events.bus import EventBus
from app.events.registry import EventRegistry
from app.providers.discovery import build_registry


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url_override="sqlite+aiosqlite:///:memory:")


@pytest.fixture
async def app_state(settings: Settings) -> AsyncIterator[AppState]:
    import fakeredis.aioredis

    db = Database(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    cache = RedisCache.__new__(RedisCache)
    cache._settings = settings
    cache._client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    cache._pool = None

    state = AppState(
        settings=settings,
        db=db,
        cache=cache,
        providers=build_registry(),
        events=EventBus(EventRegistry()),
    )
    try:
        yield state
    finally:
        await cache.client.aclose()
        await db.dispose()
