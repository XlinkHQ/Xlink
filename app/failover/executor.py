from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.session import Database
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.profile import Profile
from app.domain.user import User
from app.events.bus import EventBus
from app.events.models import SubscriptionGenerated
from app.failover.models import FailoverPlan, FailoverResult
from app.providers.base.models import ClientSpec
from app.providers.base.registry import ProviderRegistry

logger = get_logger("xlink.failover")

_DEFAULT_CONCURRENCY = 5


@dataclass(frozen=True, slots=True)
class _MigrationContext:
    assignment_id: uuid.UUID
    user_id: uuid.UUID
    profile_id: uuid.UUID
    provider_kind: object
    target_node_id: uuid.UUID
    email: str | None
    profile_slug: str
    profile_protocol: str
    profile_settings: dict
    expires_at: object
    traffic_limit_bytes: int | None


class FailoverExecutor:
    def __init__(
        self,
        db: Database,
        providers: ProviderRegistry,
        events: EventBus | None = None,
        *,
        concurrency: int = _DEFAULT_CONCURRENCY,
    ) -> None:
        self._db = db
        self._providers = providers
        self._events = events
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
        return FailoverResult(
            plan_id=plan.plan_id,
            migrated=migrated,
            skipped=skipped,
            dry_run=False,
        )

    async def _migrate_item(self, item) -> bool:
        async with self._semaphore:
            ctx = await self._load_context(item)
            if ctx is None:
                return False
            provider = self._providers.get_by_kind(ctx.provider_kind)
            new_id = uuid.uuid4()
            try:
                result = await provider.create_client(
                    ClientSpec(
                        client_id=str(new_id),
                        email=ctx.email,
                        inbound_tag=ctx.profile_slug,
                        attributes={**ctx.profile_settings, "protocol": ctx.profile_protocol},
                    )
                )
            except Exception:
                logger.warning("failover_provider_failed", assignment_id=str(ctx.assignment_id))
                return False
            committed = await self._commit_migration(ctx, new_id, result.client_id)
            if committed and self._events is not None:
                await self._events.publish(
                    SubscriptionGenerated(
                        scope="user",
                        subject_id=ctx.user_id,
                        content_hash="pending",
                        etag='"pending"',
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
        self, ctx: _MigrationContext, new_id: uuid.UUID, provider_client_id: str
    ) -> bool:
        async with self._db.session() as session:
            assignment = await session.get(ClientAssignment, ctx.assignment_id)
            if assignment is None or assignment.status is not AssignmentStatus.ACTIVE:
                return False
            if await self._already_migrated(session, assignment, ctx.target_node_id):
                return False
            new_assignment = ClientAssignment(
                id=new_id,
                user_id=ctx.user_id,
                profile_id=ctx.profile_id,
                node_id=ctx.target_node_id,
                provider_kind=ctx.provider_kind,
                provider_client_id=provider_client_id,
                status=AssignmentStatus.ACTIVE,
                expires_at=ctx.expires_at,
                traffic_limit_bytes=ctx.traffic_limit_bytes,
            )
            assignment.status = AssignmentStatus.DISABLED
            session.add(new_assignment)
            await session.flush()
        return True

    async def _already_migrated(
        self, session, assignment: ClientAssignment, target_node_id: uuid.UUID
    ) -> bool:
        stmt = select(ClientAssignment.id).where(
            ClientAssignment.user_id == assignment.user_id,
            ClientAssignment.profile_id == assignment.profile_id,
            ClientAssignment.node_id == target_node_id,
        )
        return await session.scalar(stmt) is not None
