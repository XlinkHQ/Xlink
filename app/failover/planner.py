from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node
from app.domain.user import User
from app.failover.models import FailoverPlan, FailoverPlanItem
from app.providers.base.registry import ProviderRegistry
from app.scheduler.models import SchedulerPolicyName, SchedulerRequest
from app.scheduler.service import SmartSchedulerService

logger = get_logger("xlink.failover.planner")


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
            select(ClientAssignment, User.pinned_node_ids)
            .join(User, ClientAssignment.user_id == User.id)
            .where(
                ClientAssignment.node_id == source_node_id,
                ClientAssignment.status == AssignmentStatus.ACTIVE,
            )
            .order_by(ClientAssignment.created_at.asc(), ClientAssignment.id.asc())
        )
        rows = (await self._session.execute(stmt)).all()

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
        for assignment, pinned_node_ids in rows:
            try:
                decision = await scheduler.choose_node(
                    SchedulerRequest(
                        profile_id=assignment.profile_id,
                        policy=policy,
                        dry_run=True,
                    )
                )
            except (NotFoundError, ValidationError) as exc:
                # choose_node raises on ordinary conditions — a disabled
                # profile, or no compatible node with headroom. Letting that
                # escape aborted the WHOLE evacuation, so a single unplaceable
                # user stranded every other user on a dead node. Worse, the
                # auto path records its cooldown before planning, so the
                # outage never retried. Skip this one, evacuate the rest.
                logger.warning(
                    "failover_assignment_unplaceable",
                    assignment_id=str(assignment.id),
                    profile_id=str(assignment.profile_id),
                    reason=getattr(exc, "code", None) or type(exc).__name__,
                )
                continue
            ordered = [c.node_id for c in decision.candidates] or [decision.node_id]
            pinned = {str(n) for n in (pinned_node_ids or [])}
            if pinned:
                ordered = [nid for nid in ordered if str(nid) in pinned]
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
