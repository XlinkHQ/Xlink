from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.redis import RedisCache
from app.db.session import Database
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.user import User

logger = get_logger("xlink.agent.ip_limit")


_IP_TTL_SECONDS = 600


def _key(user_id: uuid.UUID) -> str:
    return f"ipset:{user_id}"


class IpLimitService:
    def __init__(self, db: Database, cache: RedisCache) -> None:
        self._db = db
        self._redis = cache.client

    async def report(self, samples: Iterable[tuple[uuid.UUID, str]]) -> None:
        pairs = [(aid, ip) for aid, ip in samples if ip]
        if not pairs:
            return

        aids = list({aid for aid, _ in pairs})
        async with self._db.session() as session:
            rows = (
                await session.execute(
                    select(ClientAssignment.id, ClientAssignment.user_id).where(
                        ClientAssignment.id.in_(aids)
                    )
                )
            ).all()
            owner = dict(rows)

        touched: set[uuid.UUID] = set()
        for aid, ip in pairs:
            uid = owner.get(aid)
            if uid is None:
                continue
            key = _key(uid)
            await self._redis.sadd(key, ip)
            await self._redis.expire(key, _IP_TTL_SECONDS)
            touched.add(uid)

        for uid in touched:
            await self._enforce(uid)

    async def _enforce(self, user_id: uuid.UUID) -> None:
        async with self._db.session() as session:
            user = await session.get(User, user_id)
            if user is None or user.device_limit is None or user.device_limit <= 0:
                return
            count = await self._redis.scard(_key(user_id))
            if count <= user.device_limit:
                return

            rows = (
                (
                    await session.execute(
                        select(ClientAssignment)
                        .where(
                            ClientAssignment.user_id == user_id,
                            ClientAssignment.status == AssignmentStatus.ACTIVE,
                        )
                        .order_by(ClientAssignment.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            # Disable only the excess beyond device_limit (oldest first), not all.
            excess = len(rows) - user.device_limit
            if excess <= 0:
                return
            for a in rows[:excess]:
                a.status = AssignmentStatus.DISABLED
            await session.commit()
            logger.warning(
                "device_limit_exceeded_disabled",
                user_id=str(user_id),
                distinct_ips=count,
                device_limit=user.device_limit,
                disabled=excess,
            )
