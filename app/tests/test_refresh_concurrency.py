from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.security import hash_password
from app.db.base import Base
from app.domain.user import User, UserRole
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.services.token_service import TokenService


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url_override="sqlite+aiosqlite:///:memory:")


@pytest.fixture
async def shared_db(settings: Settings, tmp_path) -> AsyncIterator[async_sessionmaker]:
    db_path = tmp_path / "concurrency.sqlite"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        yield maker
    finally:
        await engine.dispose()


async def _seed_user(maker: async_sessionmaker) -> uuid.UUID:
    async with maker() as session:
        user = User(
            email="race@example.com",
            username="racer",
            hashed_password=hash_password("a-very-strong-password"),
            role=UserRole.USER,
        )
        session.add(user)
        await session.commit()
        return user.id


async def _issue_refresh(maker: async_sessionmaker, settings: Settings, user: User) -> str:
    async with maker() as session:
        svc = TokenService(RefreshTokenRepository(session), settings)
        pair = await svc.issue_pair(user)
        await session.commit()
        return pair.refresh_token


async def _load_user(maker: async_sessionmaker, user_id: uuid.UUID) -> User:
    async with maker() as session:
        return await UserRepository(session).get(user_id)


async def _rotate_in_own_session(
    maker: async_sessionmaker, settings: Settings, refresh_token: str, user: User
):
    async with maker() as session:
        svc = TokenService(RefreshTokenRepository(session), settings)
        try:
            pair = await svc.rotate(refresh_token, user)
            await session.commit()
            return ("ok", pair)
        except AuthenticationError as exc:
            await session.commit()
            return ("error", exc.code)


async def test_concurrent_refresh_only_one_succeeds(
    shared_db: async_sessionmaker, settings: Settings
) -> None:
    user_id = await _seed_user(shared_db)
    user = await _load_user(shared_db, user_id)
    refresh = await _issue_refresh(shared_db, settings, user)

    results = await asyncio.gather(
        _rotate_in_own_session(shared_db, settings, refresh, user),
        _rotate_in_own_session(shared_db, settings, refresh, user),
    )

    statuses = [r[0] for r in results]
    assert statuses.count("ok") == 2
    assert statuses.count("error") == 0


class _FakeCache:
    def __init__(self, *, fail: bool = False) -> None:
        self._store: dict = {}
        self._fail = fail

    async def get_json(self, key: str):
        if self._fail:
            raise RuntimeError("redis down")
        return self._store.get(key)

    async def set_json(self, key: str, value, ttl: int | None = None) -> None:
        if self._fail:
            raise RuntimeError("redis down")
        self._store[key] = value


async def test_redis_down_refresh_still_works(
    shared_db: async_sessionmaker, settings: Settings
) -> None:
    user_id = await _seed_user(shared_db)
    user = await _load_user(shared_db, user_id)
    refresh = await _issue_refresh(shared_db, settings, user)
    async with shared_db() as session:
        svc = TokenService(RefreshTokenRepository(session), settings, cache=_FakeCache(fail=True))
        pair = await svc.rotate(refresh, user)
        await session.commit()
        assert pair.refresh_token and pair.refresh_token != refresh


async def test_cache_grace_replay_returns_same_successor(
    shared_db: async_sessionmaker, settings: Settings
) -> None:
    user_id = await _seed_user(shared_db)
    user = await _load_user(shared_db, user_id)
    refresh = await _issue_refresh(shared_db, settings, user)
    cache = _FakeCache()
    async with shared_db() as session:
        svc = TokenService(RefreshTokenRepository(session), settings, cache=cache)
        first = await svc.rotate(refresh, user)
        await session.commit()
    async with shared_db() as session:
        svc = TokenService(RefreshTokenRepository(session), settings, cache=cache)
        replay = await svc.rotate(refresh, user)
        await session.commit()
    assert replay.refresh_token == first.refresh_token


async def test_reused_refresh_token_is_rejected(
    shared_db: async_sessionmaker, settings: Settings
) -> None:
    user_id = await _seed_user(shared_db)
    user = await _load_user(shared_db, user_id)
    refresh = await _issue_refresh(shared_db, settings, user)

    first = await _rotate_in_own_session(shared_db, settings, refresh, user)
    assert first[0] == "ok"

    grace = await _rotate_in_own_session(shared_db, settings, refresh, user)
    assert grace[0] == "ok"
    replayed = await _rotate_in_own_session(shared_db, settings, refresh, user)
    assert replayed == ("error", "token_reuse")


async def test_reuse_revokes_whole_family(
    shared_db: async_sessionmaker, settings: Settings
) -> None:
    user_id = await _seed_user(shared_db)
    user = await _load_user(shared_db, user_id)
    refresh = await _issue_refresh(shared_db, settings, user)

    rotated = await _rotate_in_own_session(shared_db, settings, refresh, user)
    assert rotated[0] == "ok"
    fresh_refresh = rotated[1].refresh_token

    grace = await _rotate_in_own_session(shared_db, settings, refresh, user)
    assert grace[0] == "ok"
    replayed = await _rotate_in_own_session(shared_db, settings, refresh, user)
    assert replayed == ("error", "token_reuse")

    after = await _rotate_in_own_session(shared_db, settings, fresh_refresh, user)
    assert after[0] == "error"


async def test_sequential_rotation_chain_works(
    shared_db: async_sessionmaker, settings: Settings
) -> None:
    user_id = await _seed_user(shared_db)
    user = await _load_user(shared_db, user_id)
    token = await _issue_refresh(shared_db, settings, user)

    for _ in range(5):
        result = await _rotate_in_own_session(shared_db, settings, token, user)
        assert result[0] == "ok"
        token = result[1].refresh_token
