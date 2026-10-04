"""First-run setup: claim an empty panel with a one-time token.

While no admin exists, the panel mints a random token (shared through Redis
so every API replica agrees) and writes it to the log. Creating the first
sudo admin requires that token, so a stranger who reaches a fresh install
before its operator cannot claim it. The token is consumed with GETDEL: of
two racing requests exactly one wins, and a wrong guess never burns it.
"""

from __future__ import annotations

import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import RedisCache
from app.domain.user import User, UserRole

TOKEN_KEY = "setup:token"
TOKEN_TTL_S = 24 * 3600


async def needs_setup(session: AsyncSession) -> bool:
    found = await session.scalar(select(User.id).where(User.role == UserRole.ADMIN).limit(1))
    return found is None


async def ensure_token(cache: RedisCache) -> str:
    """Return the live setup token, minting one if none exists."""
    await cache.client.set(TOKEN_KEY, secrets.token_urlsafe(24), nx=True, ex=TOKEN_TTL_S)
    raw = await cache.client.get(TOKEN_KEY)
    return raw.decode() if isinstance(raw, bytes) else str(raw)


async def consume_token(cache: RedisCache, supplied: str) -> bool:
    raw = await cache.client.get(TOKEN_KEY)
    if raw is None:
        return False
    current = raw.decode() if isinstance(raw, bytes) else str(raw)
    if not hmac.compare_digest(current.encode(), supplied.encode()):
        return False
    taken = await cache.client.getdel(TOKEN_KEY)
    return taken is not None and hmac.compare_digest(
        (taken.decode() if isinstance(taken, bytes) else str(taken)).encode(), supplied.encode()
    )


async def restore_token(cache: RedisCache, token: str) -> None:
    await cache.client.set(TOKEN_KEY, token, nx=True, ex=TOKEN_TTL_S)
