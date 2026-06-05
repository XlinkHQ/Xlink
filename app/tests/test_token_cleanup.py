from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings
from app.core.jobs import TokenCleanupJob, purge_expired_tokens
from app.db.base import Base
from app.db.session import Database
from app.domain.refresh_token import RefreshToken
from app.domain.user import User, UserRole


@pytest.fixture
async def db(tmp_path) -> AsyncIterator[Database]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'cleanup.sqlite'}"
    settings = Settings(database_url_override=url)
    database = Database(settings)
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield database
    finally:
        await database.dispose()


async def _seed(db: Database) -> uuid.UUID:
    now = datetime.now(UTC)
    async with db.session() as session:
        user = User(
            email="cleanup@example.com",
            username="cleanup",
            hashed_password="x",
            role=UserRole.USER,
        )
        session.add(user)
        await session.flush()
        session.add_all(
            [
                RefreshToken(
                    user_id=user.id,
                    jti=uuid.uuid4().hex,
                    token_hash="h",
                    expires_at=now - timedelta(days=1),
                ),
                RefreshToken(
                    user_id=user.id,
                    jti=uuid.uuid4().hex,
                    token_hash="h",
                    expires_at=now - timedelta(hours=1),
                ),
                RefreshToken(
                    user_id=user.id,
                    jti=uuid.uuid4().hex,
                    token_hash="h",
                    expires_at=now + timedelta(days=1),
                ),
            ]
        )
        return user.id


async def _count_tokens(db: Database) -> int:
    from sqlalchemy import func, select

    async with db.session() as session:
        return int(await session.scalar(select(func.count()).select_from(RefreshToken)) or 0)


async def test_purge_deletes_only_expired(db: Database) -> None:
    await _seed(db)
    assert await _count_tokens(db) == 3

    deleted = await purge_expired_tokens(db)
    assert deleted == 2
    assert await _count_tokens(db) == 1


async def test_purge_is_idempotent(db: Database) -> None:
    await _seed(db)
    await purge_expired_tokens(db)
    second = await purge_expired_tokens(db)
    assert second == 0


async def test_cleanup_job_runs_on_interval(db: Database) -> None:
    await _seed(db)
    job = TokenCleanupJob(db, interval_seconds=0)
    job.start()
    for _ in range(50):
        if await _count_tokens(db) == 1:
            break
        await asyncio.sleep(0.02)
    await job.stop()
    assert await _count_tokens(db) == 1


async def test_cleanup_job_stop_is_safe_without_start(db: Database) -> None:
    job = TokenCleanupJob(db, interval_seconds=60)
    await job.stop()


async def test_cleanup_job_double_start_is_safe(db: Database) -> None:
    job = TokenCleanupJob(db, interval_seconds=60)
    job.start()
    job.start()
    await job.stop()
