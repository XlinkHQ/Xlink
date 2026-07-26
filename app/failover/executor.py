from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update

from app.core.logging import get_logger
from app.db.session import Database
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node
from app.domain.profile import Profile
from app.domain.user import User
from app.events.bus import EventBus
from app.failover.models import FailoverPlan, FailoverResult
from app.providers.base.models import ClientSpec, ProviderKind
from app.providers.base.registry import ProviderRegistry

logger = get_logger("xlink.failover")

_DEFAULT_CONCURRENCY = 5


@dataclass(frozen=True, slots=True)
class _MigrationContext:
    assignment_id: uuid.UUID
    user_id: uuid.UUID
    profile_id: uuid.UUID
    provider_kind: ProviderKind
    target_node_id: uuid.UUID
    email: str | None
    profile_slug: str
    profile_protocol: str
    profile_settings: dict[str, Any]
    expires_at: datetime | None
    traffic_limit_bytes: int | None


class FailoverExecutor:
    def __init__(
        self,
        db: Database,
        providers: ProviderRegistry,
        events: EventBus | None = None,
        *,
        concurrency: int = _DEFAULT_CONCURRENCY,
        cache=None,
    ) -> None:
        self._db = db
        self._providers = providers
        self._events = events
        self._cache = cache
        self._semaphore = asyncio.Semaphore(max(1, concurrency))

    async def execute(self, plan: FailoverPlan) -> FailoverResult:
        if plan.dry_run:
            return FailoverResult(
                plan_id=plan.plan_id,
                migrated=0,
                skipped=len(plan.items),
                dry_run=True,
            )

        outcomes = await asyncio.gather(*(self._migrate_item(item) for item in plan.items))
        migrated = sum(1 for ok in outcomes if ok)
        skipped = len(outcomes) - migrated
        if migrated:
            await self._wake_after_migration(plan)
        return FailoverResult(
            plan_id=plan.plan_id,
            migrated=migrated,
            skipped=skipped,
            dry_run=False,
        )

    async def _wake_after_migration(self, plan: FailoverPlan) -> None:
        if self._cache is None:
            return
        node_ids = {plan.source_node_id}
        node_ids.update(i.target_node_id for i in plan.items if i.target_node_id is not None)
        try:
            for uid in {i.user_id for i in plan.items}:
                await self._cache.incr(f"subscription:rev:{uid}")
            for nid in node_ids:
                await self._cache.publish_node_event(nid, "config_changed")
        except Exception as exc:
            logger.warning("failover_cache_invalidate_failed", error=str(exc))

    async def _migrate_item(self, item) -> bool:
        async with self._semaphore:
            try:
                ctx = await self._load_context(item)
            except Exception:
                logger.exception(
                    "failover_load_context_failed",
                    assignment_id=str(getattr(item, "assignment_id", None)),
                )
                return False
            if ctx is None:
                return False
            new_id = uuid.uuid4()
            try:
                provider = self._providers.get_by_kind(ctx.provider_kind)
                result = await provider.create_client(
                    ClientSpec(
                        client_id=str(new_id),
                        email=ctx.email,
                        inbound_tag=ctx.profile_slug,
                        attributes={**ctx.profile_settings, "protocol": ctx.profile_protocol},
                    )
                )
            except Exception:
                logger.exception("failover_provider_failed", assignment_id=str(ctx.assignment_id))
                return False
            try:
                committed = await self._commit_migration(ctx, new_id, result.client_id, result.raw)
            except Exception:
                logger.exception("failover_commit_failed", assignment_id=str(ctx.assignment_id))
                committed = False
            if not committed:
                try:
                    await provider.delete_client(result.client_id)
                except Exception:
                    logger.warning(
                        "failover_orphan_cleanup_failed",
                        assignment_id=str(ctx.assignment_id),
                        client_id=result.client_id,
                    )
                return False
            if committed and self._events is not None:
                from app.events.models import SubscriptionGenerated

                await self._events.publish(
                    SubscriptionGenerated(
                        scope="user",
                        subject_id=ctx.user_id,
                        content_hash="",
                        etag="",
                        item_count=0,
                    )
                )
            return committed

    async def _load_context(self, item) -> _MigrationContext | None:
        async with self._db.session() as session:
            assignment = await session.get(ClientAssignment, item.assignment_id)
            if assignment is None or assignment.status is not AssignmentStatus.ACTIVE:
                return None
            if await self._already_migrated(session, assignment, item.target_node_id):
                return None
            profile = await session.get(Profile, item.profile_id)
            user = await session.get(User, item.user_id)
            if profile is None or user is None:
                return None
            return _MigrationContext(
                assignment_id=assignment.id,
                user_id=assignment.user_id,
                profile_id=assignment.profile_id,
                provider_kind=assignment.provider_kind,
                target_node_id=item.target_node_id,
                email=user.email,
                profile_slug=profile.slug,
                profile_protocol=profile.protocol,
                profile_settings=dict(profile.settings),
                expires_at=assignment.expires_at,
                traffic_limit_bytes=assignment.traffic_limit_bytes,
            )

    async def _commit_migration(
        self,
        ctx: _MigrationContext,
        new_id: uuid.UUID,
        provider_client_id: str,
        credentials: object = None,
    ) -> bool:
        async with self._db.session() as session:
            assignment = await session.get(ClientAssignment, ctx.assignment_id)
            if assignment is None or assignment.status is not AssignmentStatus.ACTIVE:
                return False
            if await self._already_migrated(session, assignment, ctx.target_node_id):
                return False

            target_node = await session.get(Node, ctx.target_node_id)
            if target_node is not None:
                stmt = update(Node).where(Node.id == ctx.target_node_id)
                if target_node.max_users is not None:
                    stmt = stmt.where(Node.current_users < target_node.max_users)
                result = await session.execute(
                    stmt.values(current_users=Node.current_users + 1).execution_options(
                        synchronize_session=False
                    )
                )
                if (result.rowcount or 0) == 0:
                    logger.warning(
                        "failover_target_at_capacity",
                        assignment_id=str(ctx.assignment_id),
                        target_node_id=str(ctx.target_node_id),
                    )
                    return False

            await session.execute(
                delete(ClientAssignment).where(
                    ClientAssignment.user_id == ctx.user_id,
                    ClientAssignment.profile_id == ctx.profile_id,
                    ClientAssignment.node_id == ctx.target_node_id,
                    ClientAssignment.status != AssignmentStatus.ACTIVE,
                )
            )

            new_assignment = ClientAssignment(
                id=new_id,
                user_id=ctx.user_id,
                profile_id=ctx.profile_id,
                node_id=ctx.target_node_id,
                provider_kind=ctx.provider_kind,
                provider_client_id=provider_client_id,
                credentials=dict(credentials) if isinstance(credentials, dict) else {},
                status=AssignmentStatus.ACTIVE,
                expires_at=ctx.expires_at,
                traffic_limit_bytes=ctx.traffic_limit_bytes,
            )
            assignment.status = AssignmentStatus.DISABLED
            session.add(new_assignment)
            await session.flush()

            for node_id in {ctx.target_node_id, assignment.node_id}:
                if node_id is None:
                    continue
                await session.execute(
                    update(Node)
                    .where(Node.id == node_id)
                    .values(
                        current_users=(
                            select(func.count())
                            .select_from(ClientAssignment)
                            .where(
                                ClientAssignment.node_id == node_id,
                                ClientAssignment.status == AssignmentStatus.ACTIVE,
                            )
                            .scalar_subquery()
                        )
                    )
                    .execution_options(synchronize_session=False)
                )
            await session.flush()
        return True

    async def _already_migrated(
        self, session, assignment: ClientAssignment, target_node_id: uuid.UUID
    ) -> bool:
        stmt = select(ClientAssignment.id).where(
            ClientAssignment.user_id == assignment.user_id,
            ClientAssignment.profile_id == assignment.profile_id,
            ClientAssignment.node_id == target_node_id,
            ClientAssignment.status == AssignmentStatus.ACTIVE,
        )
        return await session.scalar(stmt) is not None
