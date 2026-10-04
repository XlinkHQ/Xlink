"""Logout must actually revoke.

Two independent grace paths made a revoked refresh token replayable:

1. `rotate()` answers from the Redis grace cache BEFORE it reads the database,
   so `revoked=True` was invisible while the cached successor lived.
2. `_consume()` keeps a second, DB-level reuse-grace window keyed on
   `revoked_at >= cutoff` + `claim_grace`. `revoke_all_for_user` filtered on
   `revoked == False`, so it skipped the row `rotate()` had just revoked and
   never burned that row's grace slot.

Both are closed here. These tests fail against either regression.
"""

from __future__ import annotations

import fakeredis.aioredis
import pytest

from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.security import hash_password
from app.db.base import Base
from app.db.redis import RedisCache
from app.db.session import Database
from app.domain.user import User, UserRole
from app.repositories.refresh_token import RefreshTokenRepository
from app.services.token_service import TokenService


@pytest.fixture
async def ctx():
    settings = Settings(database_url_override="sqlite+aiosqlite:///:memory:")
    db = Database(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    cache = RedisCache.__new__(RedisCache)
    cache._settings = settings
    cache._pool = None
    cache._client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    async with db.session() as session:
        user = User(
            username="revoke-me",
            hashed_password=hash_password("strong-password-1234-AB!"),
            role=UserRole.ADMIN,
            is_sudo=True,
        )
        session.add(user)
        await session.flush()
        svc = TokenService(RefreshTokenRepository(session), settings, cache=cache)
        yield svc, user, cache
    await cache.client.aclose()
    await db.dispose()


async def test_logout_kills_a_rotated_token(ctx) -> None:
    svc, user, _ = ctx
    stolen = (await svc.issue_pair(user)).refresh_token
    await svc.rotate(stolen, user)

    await svc.revoke(stolen)  # /auth/logout

    with pytest.raises(AuthenticationError):
        await svc.rotate(stolen, user)


async def test_logout_all_kills_a_rotated_token(ctx) -> None:
    """The 'my account is compromised' button. Must beat the grace windows."""
    svc, user, _ = ctx
    stolen = (await svc.issue_pair(user)).refresh_token
    await svc.rotate(stolen, user)

    await svc.revoke_all(user.id)  # /auth/logout-all

    with pytest.raises(AuthenticationError):
        await svc.rotate(stolen, user)


async def test_logout_all_kills_the_successor_too(ctx) -> None:
    svc, user, _ = ctx
    first = (await svc.issue_pair(user)).refresh_token
    successor = (await svc.rotate(first, user)).refresh_token

    await svc.revoke_all(user.id)

    with pytest.raises(AuthenticationError):
        await svc.rotate(successor, user)


async def test_revoke_clears_the_redis_grace_entry(ctx) -> None:
    """Direct assertion on path 1: no cached successor may outlive a revoke."""
    svc, user, cache = ctx
    token = (await svc.issue_pair(user)).refresh_token
    await svc.rotate(token, user)
    assert await cache.client.keys("refresh-grace:*"), "precondition: a grace entry exists"

    await svc.revoke(token)

    assert await cache.client.keys("refresh-grace:*") == []


async def test_logout_all_clears_every_grace_entry(ctx) -> None:
    svc, user, cache = ctx
    a = (await svc.issue_pair(user)).refresh_token
    b = (await svc.issue_pair(user)).refresh_token
    await svc.rotate(a, user)
    await svc.rotate(b, user)
    assert await cache.client.keys("refresh-grace:*")

    await svc.revoke_all(user.id)

    assert await cache.client.keys("refresh-grace:*") == []


async def test_normal_rotation_still_works(ctx) -> None:
    """The fix must not break the ordinary refresh flow it guards."""
    svc, user, _ = ctx
    token = (await svc.issue_pair(user)).refresh_token
    for _ in range(3):
        token = (await svc.rotate(token, user)).refresh_token
    assert token


async def test_concurrent_refresh_still_gets_the_same_pair(ctx) -> None:
    """The grace cache exists so two tabs refreshing at once don't lock out.
    That behaviour must survive the revocation fix."""
    svc, user, _ = ctx
    token = (await svc.issue_pair(user)).refresh_token
    first = await svc.rotate(token, user)
    replay = await svc.rotate(token, user)
    assert replay.access_token == first.access_token
