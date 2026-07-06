from __future__ import annotations

from fastapi import APIRouter

from app.dependencies.auth import AdminUser, SudoAdminUser
from app.dependencies.services import SchedulerServiceDep
from app.scheduler.models import SchedulerPolicyName, SchedulerRequest
from app.scheduler.schemas import NodeScoreRead, SchedulerDecisionRead, SchedulerRequestSchema

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/policies", response_model=list[str])
async def scheduler_policies(_admin: AdminUser) -> list[str]:
    return [policy.value for policy in SchedulerPolicyName]


@router.post("/run", response_model=SchedulerDecisionRead)
async def scheduler_run(
    payload: SchedulerRequestSchema,
    _admin: SudoAdminUser,
    scheduler: SchedulerServiceDep,
) -> SchedulerDecisionRead:
    decision = await scheduler.choose_node(
        SchedulerRequest(
            profile_id=payload.profile_id,
            preferred_region=payload.preferred_region,
            policy=payload.policy,
            dry_run=payload.dry_run,
            weights=payload.weights,
        )
    )
    return SchedulerDecisionRead(
        node_id=decision.node_id,
        profile_id=decision.profile_id,
        policy=decision.policy,
        dry_run=decision.dry_run,
        score=decision.score,
        candidates=tuple(
            NodeScoreRead(node_id=c.node_id, score=c.score, reasons=c.reasons)
            for c in decision.candidates
        ),
    )
