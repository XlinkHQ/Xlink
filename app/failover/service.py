from __future__ import annotations

import uuid

from app.db.session import Database
from app.events.bus import EventBus
from app.failover.executor import FailoverExecutor
from app.failover.models import FailoverPlan, FailoverResult
from app.failover.planner import FailoverPlanner
from app.providers.base.registry import ProviderRegistry
from app.scheduler.models import SchedulerPolicyName


class FailoverService:
    def __init__(
        self,
        db: Database,
        providers: ProviderRegistry,
        events: EventBus | None = None,
        *,
        concurrency: int = 5,
    ) -> None:
        self._db = db
        self._providers = providers
        self._executor = FailoverExecutor(db, providers, events, concurrency=concurrency)

    async def plan(
        self,
        source_node_id: uuid.UUID,
        *,
        dry_run: bool = False,
        policy: SchedulerPolicyName = SchedulerPolicyName.BALANCED,
    ) -> FailoverPlan:
        async with self._db.session() as session:
            planner = FailoverPlanner(session, self._providers)
            return await planner.build_plan(source_node_id, dry_run=dry_run, policy=policy)

    async def execute(self, plan: FailoverPlan) -> FailoverResult:
        return await self._executor.execute(plan)

    async def failover_node(
        self,
        source_node_id: uuid.UUID,
        *,
        dry_run: bool = False,
        policy: SchedulerPolicyName = SchedulerPolicyName.BALANCED,
    ) -> FailoverResult:
        plan = await self.plan(source_node_id, dry_run=dry_run, policy=policy)
        return await self.execute(plan)
