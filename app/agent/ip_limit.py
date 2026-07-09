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

    async def report(
        self, samples: Iterable[tuple[uuid.UUID, str]], *, node_id: uuid.UUID | None = None
    ) -> None:
        pairs = [(aid, ip) for aid, ip in samples if ip]
        if not pairs:
            return

        aids = list({aid for aid, _ in pairs})
        async with self._db.session() as session:
            stmt = select(ClientAssignment.id, ClientAssignment.user_id).where(
                ClientAssignment.id.in_(aids)
            )
            # Only accept reports for assignments the reporting node actually
            # hosts — a node must not be able to inflate another node's users'
            # device-count ipset (and thus wrongly trip their device limit).
            if node_id is not None:
                stmt = stmt.where(ClientAssignment.node_id == node_id)
            rows = (await session.execute(stmt)).all()
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

        if not touched:
            return

        # Batch: load device limits for all touched users in one session, then
        # only the users actually over their limit incur an enforcement pass.
        async with self._db.session() as session:
            limit_rows = (
                await session.execute(
                    select(User.id, User.device_limit).where(User.id.in_(touched))
                )
            ).all()
        for uid, limit in limit_rows:
            if limit is None or limit <= 0:
                continue
            count = await self._redis.scard(_key(uid))
            if count > limit:
                await self._enforce(uid)
            else:
                await self._recover(uid)

    async def _recover(self, user_id: uuid.UUID) -> None:
        # Device count is back under the limit — re-activate assignments that WE
        # disabled for an ip-limit breach (never touch admin-disabled ones).
        from app.domain.user import User

        async with self._db.session() as session:
            # If an admin disabled the user after the ip-limit trip, do NOT
            # resurrect their assignments — that would silently override the admin
            # disable. The ip_limited creds flag alone isn't enough to re-activate.
            user = await session.get(User, user_id)
            if user is None or not user.is_active or user.removed:
                return
            rows = (
                (
                    await session.execute(
                        select(ClientAssignment).where(
                            ClientAssignment.user_id == user_id,
                            ClientAssignment.status == AssignmentStatus.DISABLED,
                        )
                    )
                )
                .scalars()
                .all()
            )
            recovered_nodes: set = set()
            for a in rows:
                creds = a.credentials or {}
                if not (isinstance(creds, dict) and creds.get("ip_limited")):
                    continue
                a.status = AssignmentStatus.ACTIVE
                new_creds = dict(creds)
                new_creds.pop("ip_limited", None)
                a.credentials = new_creds
                if a.node_id is not None:
                    recovered_nodes.add(a.node_id)
            if not recovered_nodes:
                return
            await session.flush()
            from sqlalchemy import func, update

            from app.domain.node import Node

            active_count = (
                select(func.count())
                .select_from(ClientAssignment)
                .where(
                    ClientAssignment.node_id == Node.id,
                    ClientAssignment.status == AssignmentStatus.ACTIVE,
                )
                .scalar_subquery()
            )
            await session.execute(
                update(Node)
                .where(Node.id.in_(sorted(recovered_nodes)))
                .values(current_users=active_count)
                .execution_options(synchronize_session=False)
            )
            await session.commit()

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
            # Distinct source IPs exceeded the device limit: disable the oldest
            # active assignments by the overage, clamped to what exists. rows are
            # already ACTIVE-only, so rows[:excess] can't disable more than exist.
            excess = count - user.device_limit
            if excess <= 0:
                return
            doomed = rows[:excess]
            if not doomed:
                return
            doomed_nodes = sorted({a.node_id for a in doomed if a.node_id is not None})
            for a in doomed:
                a.status = AssignmentStatus.DISABLED
                # Mark WHY it was disabled so it can be auto-recovered once the
                # user's device count drops back under the limit (vs an admin
                # disable, which must stay disabled).
                creds = dict(a.credentials or {})
                creds["ip_limited"] = True
                a.credentials = creds
            await session.flush()
            if doomed_nodes:
                from sqlalchemy import func, update

                from app.domain.node import Node

                active_count = (
                    select(func.count())
                    .select_from(ClientAssignment)
                    .where(
                        ClientAssignment.node_id == Node.id,
                        ClientAssignment.status == AssignmentStatus.ACTIVE,
                    )
                    .scalar_subquery()
                )
                await session.execute(
                    update(Node)
                    .where(Node.id.in_(doomed_nodes))
                    .values(current_users=active_count)
                    .execution_options(synchronize_session=False)
                )
            await session.commit()
            logger.warning(
                "device_limit_exceeded_disabled",
                user_id=str(user_id),
                distinct_ips=count,
                device_limit=user.device_limit,
                disabled=len(doomed),
            )
