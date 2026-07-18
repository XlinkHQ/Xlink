from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select, update

from app.core.cache import CacheProtocol
from app.core.leader import LeaderElector
from app.core.logging import get_logger
from app.db.session import Database
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.user import User
from app.events.bus import EventBus
from app.events.models import AssignmentExpired
from app.repositories.refresh_token import RefreshTokenRepository

logger = get_logger("xlink.jobs")


async def purge_expired_tokens(db: Database) -> int:
    async with db.session() as session:
        repo = RefreshTokenRepository(session)
        deleted = await repo.delete_expired(datetime.now(UTC))
    if deleted:
        logger.info("expired_tokens_purged", deleted=deleted)
    return deleted


class TokenCleanupJob:
    def __init__(
        self, db: Database, *, interval_seconds: int, leader: LeaderElector | None = None
    ) -> None:
        self._db = db
        self._interval = interval_seconds
        self._leader = leader
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="token-cleanup")
        logger.info("token_cleanup_started", interval_seconds=self._interval)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        logger.info("token_cleanup_stopped")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._stopping.is_set():
                break
            if self._leader is not None and not self._leader.is_leader:
                continue
            try:
                await purge_expired_tokens(self._db)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("token_cleanup_failed")


class AssignmentExpirationJob:
    def __init__(
        self,
        db: Database,
        events: EventBus,
        *,
        interval_seconds: int,
        cache: CacheProtocol | None = None,
        leader: LeaderElector | None = None,
    ) -> None:
        self._db = db
        self._events = events
        self._interval = interval_seconds
        self._cache = cache
        self._leader = leader
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="assignment-expiration")
        logger.info("assignment_expiration_started", interval_seconds=self._interval)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        logger.info("assignment_expiration_stopped")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._stopping.is_set():
                break
            if self._leader is not None and not self._leader.is_leader:
                continue
            try:
                await self._expire_assignments()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("assignment_expiration_failed")

    async def _expire_assignments(self) -> None:
        now = datetime.now(UTC)
        node_ids: list = []
        async with self._db.session() as session:
            stmt = (
                select(ClientAssignment)
                .join(User, ClientAssignment.user_id == User.id)
                .where(
                    ClientAssignment.status == AssignmentStatus.ACTIVE,
                    or_(
                        and_(
                            ClientAssignment.expires_at.isnot(None),
                            ClientAssignment.expires_at < now,
                        ),
                        and_(User.expire_at.isnot(None), User.expire_at < now),
                        # On-hold users that were never activated before their
                        # activation deadline expire instead of being served forever.
                        and_(
                            User.on_hold.is_(True),
                            User.activation_deadline.isnot(None),
                            User.activation_deadline < now,
                        ),
                    ),
                )
                # Cap per run so a large backlog (clock jump / long downtime) doesn't
                # load the entire expired set into memory; the rest expires next cycle.
                .limit(5000)
            )
            result = await session.execute(stmt)
            expired = result.scalars().all()

            if not expired:
                return

            ids = [a.id for a in expired]
            node_ids = sorted({a.node_id for a in expired if a.node_id is not None})
            await session.execute(
                update(ClientAssignment)
                .where(ClientAssignment.id.in_(ids))
                .values(status=AssignmentStatus.EXPIRED)
            )
            # Close the on-hold escape hatch: an on-hold user whose activation
            # deadline passed must have on_hold cleared + expire_at set to now, or a
            # later quota/expiry edit re-activates them (expire_at is None → looks
            # "not expired") and hands out free service. Mirror activate_on_hold.
            await session.execute(
                update(User)
                .where(
                    User.on_hold.is_(True),
                    User.activation_deadline.isnot(None),
                    User.activation_deadline < now,
                )
                .values(on_hold=False, expire_at=now)
                .execution_options(synchronize_session=False)
            )
            if node_ids:
                from sqlalchemy import func

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
                    .where(Node.id.in_(node_ids))
                    .values(current_users=active_count)
                    .execution_options(synchronize_session=False)
                )
            await session.commit()

        await self._wake_nodes(node_ids)

        for assignment in expired:
            logger.info(
                "assignment_expired",
                assignment_id=str(assignment.id),
                user_id=str(assignment.user_id),
                expires_at=str(assignment.expires_at),
            )
            self._events.publish_background(
                AssignmentExpired(
                    assignment_id=assignment.id,
                    user_id=assignment.user_id,
                    expired_at=assignment.expires_at or now,
                    provider_kind=assignment.provider_kind,
                )
            )

        logger.info("assignment_expiration_batch_complete", count=len(expired))

    async def _wake_nodes(self, node_ids: list) -> None:
        if self._cache is None or not node_ids:
            return
        # Broad invalidation is O(1): bump the global subscription cache epoch so
        # every cached feed goes stale at once, instead of a SCAN+DEL over the
        # whole subscription:* keyspace (which stampeded every user into a
        # recompute). Stale keys expire by TTL.
        await self._cache.incr("subscription:rev:__global__")
        for nid in node_ids:
            await self._cache.publish_node_event(nid, "config_changed")
