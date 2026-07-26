from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import Database

STRONG = "read-replica-secret-key-32-chars-9xZ!"


def _settings(**kw) -> Settings:
    base = {"jwt_secret_key": STRONG, "_env_file": None}
    base.update(kw)
    return Settings(**base)


def test_no_replica_by_default():
    s = _settings()
    assert s.database_url_replica is None
    assert s.has_read_replica is False


def test_replica_override_wins():
    s = _settings(
        database_url_replica_override="postgresql+asyncpg://u:p@replica/db",
        postgres_replica_host="ignored-host",
    )
    assert s.database_url_replica == "postgresql+asyncpg://u:p@replica/db"
    assert s.has_read_replica is True


def test_replica_from_host_reuses_primary_credentials():
    s = _settings(
        postgres_replica_host="standby.internal",
        postgres_user="xlink",
        postgres_password="a-strong-pg-pass-value",
        postgres_db="xlink",
        postgres_port=6432,
    )
    url = s.database_url_replica
    assert url is not None
    assert "standby.internal" in url
    assert ":6432" in url
    assert "/xlink" in url


async def test_reader_falls_back_to_primary_when_unconfigured():
    db = Database(_settings(database_url_override="sqlite+aiosqlite:///:memory:"))
    try:
        assert db.has_replica is False
        assert db.reader_sessionmaker is db.sessionmaker
    finally:
        await db.dispose()


async def test_reader_session_reads_primary_data_when_unconfigured(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'rr.sqlite'}"
    db = Database(_settings(database_url_override=url))
    try:
        async with db.session() as s:
            await s.execute(text("CREATE TABLE t (v INTEGER)"))
            await s.execute(text("INSERT INTO t (v) VALUES (42)"))
        async with db.reader_session() as r:
            got = (await r.execute(text("SELECT v FROM t"))).scalar_one()
        assert got == 42
    finally:
        await db.dispose()


async def test_second_engine_built_and_disposed_when_replica_set(tmp_path):
    primary = f"sqlite+aiosqlite:///{tmp_path / 'primary.sqlite'}"
    replica = f"sqlite+aiosqlite:///{tmp_path / 'replica.sqlite'}"
    db = Database(
        _settings(
            database_url_override=primary,
            database_url_replica_override=replica,
        )
    )
    try:
        assert db.has_replica is True
        assert db.reader_sessionmaker is not db.sessionmaker
        assert db.reader_engine is not None
        assert db.reader_engine is not db.engine
        async with db.reader_session() as r:
            assert r.bind is db.reader_engine
    finally:
        await db.dispose()


async def test_reader_dep_is_wired(app_state):
    from app.dependencies.core import get_reader_session

    agen = get_reader_session(app_state)
    session = await agen.__anext__()
    try:
        one = (await session.execute(text("SELECT 1"))).scalar_one()
        assert one == 1
    finally:
        with pytest.raises(StopAsyncIteration):
            await agen.__anext__()


async def test_traffic_service_reader_falls_back_to_primary(app_state):
    from app.traffic.service import TrafficService

    async with app_state.db.session() as write_s, app_state.db.reader_session() as read_s:
        svc = TrafficService(write_s, reader_session=read_s)
        totals = await svc.totals()
        assert totals.total_bytes == 0
        by_node = await svc.usage_by_node()
        assert by_node == {}
