from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.refresh_token import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        return await self.get_by(jti=jti)

    async def consume_active(self, jti: str) -> RefreshToken | None:
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.jti == jti, RefreshToken.revoked.is_(False))
            .values(revoked=True)
            .returning(RefreshToken)
            .execution_options(populate_existing=True)
        )
        return result.scalars().one_or_none()

    async def claim_grace(self, jti: str) -> bool:
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.jti == jti, RefreshToken.grace_used.is_(False))
            .values(grace_used=True)
        )
        return (result.rowcount or 0) == 1

    async def revoke_by_jti(self, jti: str) -> int:

        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.jti == jti)
            .values(revoked=True, grace_used=True)
        )
        return result.rowcount or 0

    async def recent_jtis_for_user(self, user_id: uuid.UUID) -> list[str]:
        """Every jti for this user, revoked ones INCLUDED.

        The token service clears each one's Redis grace entry on logout-all.
        Already-revoked jtis matter most: rotate() marks a token revoked and
        then caches its successor, so the replayable grace entries hang off
        exactly the rows a `revoked == False` filter would skip.
        """
        result = await self.session.execute(
            select(RefreshToken.jti).where(RefreshToken.user_id == user_id)
        )
        return list(result.scalars().all())

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke every unexpired token for this user and burn its grace slot.

        Deliberately NOT filtered on ``revoked == False``: rotate() revokes a
        token and then leaves a short reuse-grace window open on that same row
        (_consume checks ``revoked_at >= cutoff`` and ``claim_grace``). Skipping
        already-revoked rows left that window open, so a stolen pre-rotation
        token still replayed straight through a logout-all.
        """
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .values(revoked=True, grace_used=True)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount or 0

    async def delete_expired(self, now: datetime) -> int:
        result = await self.session.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < now)
        )
        return result.rowcount or 0
