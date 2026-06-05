from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.failover.models import FailoverPlan, FailoverPlanItem
from app.providers.base.registry import ProviderRegistry
from app.scheduler.models import SchedulerPolicyName, SchedulerRequest
from app.scheduler.service import SmartSchedulerService


class FailoverPlanner:
    def __init__(self, session: AsyncSession, providers: ProviderRegistry) -> None:
        self._session = session
        self._providers = providers

    async def build_plan(
        self,
        source_node_id: uuid.UUID,
        *,
        dry_run: bool = False,
        policy: SchedulerPolicyName = SchedulerPolicyName.BALANCED,
    ) -> FailoverPlan:
        scheduler = SmartSchedulerService(self._session, self._providers)
        stmt = (
            select(ClientAssignment)
            .where(
                ClientAssignment.node_id == source_node_id,
                ClientAssignment.status == AssignmentStatus.ACTIVE,
            )
            .order_by(ClientAssignment.created_at.asc(), ClientAssignment.id.asc())
        )
        assignments = (await self._session.execute(stmt)).scalars().all()
        items: list[FailoverPlanItem] = []
        for assignment in assignments:
            decision = await scheduler.choose_node(
                SchedulerRequest(
                    profile_id=assignment.profile_id,
                    policy=policy,
                    dry_run=True,
                )
            )
            if decision.node_id == source_node_id:
                continue
            items.append(
                FailoverPlanItem(
                    assignment_id=assignment.id,
                    source_node_id=source_node_id,
                    target_node_id=decision.node_id,
                    profile_id=assignment.profile_id,
                    user_id=assignment.user_id,
                )
            )
        return FailoverPlan(source_node_id=source_node_id, items=tuple(items), dry_run=dry_run)
