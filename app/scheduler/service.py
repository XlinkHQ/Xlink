from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.providers.base.exceptions import ProviderNotFoundError
from app.providers.base.registry import ProviderRegistry
from app.scheduler.models import SchedulerDecision, SchedulerRequest
from app.scheduler.policies import policy_for


class SmartSchedulerService:
    def __init__(self, session: AsyncSession, providers: ProviderRegistry) -> None:
        self._session = session
        self._providers = providers

    async def choose_node(self, request: SchedulerRequest) -> SchedulerDecision:
        profile = await self._session.get(Profile, request.profile_id)
        if profile is None:
            raise NotFoundError("Profile not found.", code="profile_not_found")
        if not profile.is_active:
            raise ValidationError("Profile is disabled.", code="profile_disabled")
        try:
            self._providers.get_by_kind(profile.provider_kind)
        except ProviderNotFoundError as exc:
            raise ValidationError(
                "Provider is not registered.",
                code="scheduler_provider_unavailable",
                details={"provider_kind": profile.provider_kind.value},
            ) from exc

        nodes = await self._candidate_nodes(profile)
        if not nodes:
            raise ValidationError("No compatible node available.", code="scheduler_no_node")

        policy = policy_for(request.policy, request.weights)
        scored = tuple(
            sorted(
                (policy.score(node, preferred_region=request.preferred_region) for node in nodes),
                key=lambda item: (-item.score, str(item.node_id)),
            )
        )
        best = scored[0]
        return SchedulerDecision(
            node_id=best.node_id,
            profile_id=profile.id,
            policy=request.policy,
            dry_run=request.dry_run,
            score=best.score,
            candidates=scored,
        )

    async def _candidate_nodes(self, profile: Profile) -> tuple[Node, ...]:
        stmt = (
            select(Node)
            .where(
                Node.status == NodeStatus.ACTIVE,
                Node.current_users < Node.max_users,
            )
            .order_by(Node.created_at.asc(), Node.id.asc())
        )
        nodes = (await self._session.execute(stmt)).scalars().all()
        return tuple(node for node in nodes if self._is_provider_compatible(node, profile))

    def _is_provider_compatible(self, node: Node, profile: Profile) -> bool:
        supported = node.node_metadata.get("provider_kinds")
        if supported is None:
            return True
        if not isinstance(supported, list):
            return False
        return profile.provider_kind.value in supported
