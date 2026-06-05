from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import Database

STRONG = "audit-secret-key-32-chars-minimum-9xZ"
PG_PASS = "a-very-strong-pg-pass-9"


def _settings(**kw) -> Settings:
    base = {"jwt_secret_key": STRONG}
    base.update(kw)
    return Settings(**base)


def test_session_mode_fanout_is_worker_aware():
    s = _settings(web_concurrency=14, db_pool_size=20, db_max_overflow=10)
    assert s.db_max_total_connections == 30 * 14
    assert s.db_connection_safe is False


def test_safe_defaults_single_worker():
    s = _settings()
    assert s.db_max_total_connections == 20
    assert s.db_connection_safe is True


def test_pgbouncer_mode_bounds_by_workers():
    s = _settings(web_concurrency=14, db_pool_mode="transaction")
    assert s.db_uses_pgbouncer is True
    assert s.db_max_total_connections == 14
    assert s.db_connection_safe is True


def test_production_rejects_connection_explosion():
    with pytest.raises(ValueError, match="fan-out"):
        _settings(
            env="production",
            web_concurrency=14,
            trusted_hosts=["api.x.io"],
            postgres_password=PG_PASS,
        )


def test_production_pgbouncer_mitigates():
    s = _settings(
        env="production",
        web_concurrency=14,
        db_pool_mode="transaction",
        trusted_hosts=["api.x.io"],
        postgres_password=PG_PASS,
    )
    assert s.db_connection_safe is True


async def test_pool_stats_diagnostics():
    db = Database(_settings(database_url_override="sqlite+aiosqlite:///:memory:"))
    stats = db.pool_stats()
    assert "pool_class" in stats
    assert stats["mode"] == "session"
    assert "max_total_connections" in stats
    await db.dispose()


async def test_concurrent_sessions_recover(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'pool.sqlite'}"
    db = Database(_settings(database_url_override=url))

    async def ping_once() -> int:
        async with db.session() as session:
            result = await session.execute(text("SELECT 1"))
            return int(result.scalar() or 0)

    results = await asyncio.gather(*[ping_once() for _ in range(50)])
    assert all(r == 1 for r in results)
    assert await ping_once() == 1
    await db.dispose()
