from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, update
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

    async def revoke_by_jti(self, jti: str) -> int:
        result = await self.session.execute(
            update(RefreshToken).where(RefreshToken.jti == jti).values(revoked=True)
        )
        return result.rowcount or 0

    async def revoke_all_for_user(self, user_id) -> int:
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
            .values(revoked=True)
        )
        return result.rowcount or 0

    async def delete_expired(self, now: datetime) -> int:
        result = await self.session.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < now)
        )
        return result.rowcount or 0
