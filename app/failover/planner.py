from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node
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

        # Per-target running tally so capacity is consumed as items are planned,
        # spreading load across nodes instead of piling onto a single target.
        capacity: dict[uuid.UUID, int] = {}
        planned: dict[uuid.UUID, int] = {}

        async def _headroom(node_id: uuid.UUID) -> bool:
            if node_id not in capacity:
                node = await self._session.get(Node, node_id)
                capacity[node_id] = (
                    node.max_users if node is not None and node.max_users is not None else -1
                )
                planned[node_id] = node.current_users if node is not None else 0
            cap = capacity[node_id]
            if cap < 0:
                return True
            return planned[node_id] < cap

        items: list[FailoverPlanItem] = []
        for assignment in assignments:
            decision = await scheduler.choose_node(
                SchedulerRequest(
                    profile_id=assignment.profile_id,
                    policy=policy,
                    dry_run=True,
                )
            )
            ordered = [c.node_id for c in decision.candidates] or [decision.node_id]
            target_id = None
            for candidate_id in ordered:
                if candidate_id == source_node_id:
                    continue
                if await _headroom(candidate_id):
                    target_id = candidate_id
                    break
            if target_id is None:
                continue
            planned[target_id] += 1
            items.append(
                FailoverPlanItem(
                    assignment_id=assignment.id,
                    source_node_id=source_node_id,
                    target_node_id=target_id,
                    profile_id=assignment.profile_id,
                    user_id=assignment.user_id,
                )
            )
        return FailoverPlan(source_node_id=source_node_id, items=tuple(items), dry_run=dry_run)
