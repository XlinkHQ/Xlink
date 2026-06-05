from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.dependencies.auth import AdminUser
from app.dependencies.services import FailoverServiceDep
from app.failover.models import FailoverPlan, FailoverPlanItem
from app.failover.schemas import (
    FailoverPlanItemRead,
    FailoverPlanRead,
    FailoverResultRead,
)
from app.scheduler.models import SchedulerPolicyName

router = APIRouter(prefix="/failover", tags=["failover"])


class FailoverPlanRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_node_id: uuid.UUID
    dry_run: bool = False
    policy: SchedulerPolicyName = SchedulerPolicyName.BALANCED


def _plan_read(plan: FailoverPlan) -> FailoverPlanRead:
    return FailoverPlanRead(
        plan_id=plan.plan_id,
        source_node_id=plan.source_node_id,
        dry_run=plan.dry_run,
        items=tuple(
            FailoverPlanItemRead(
                assignment_id=item.assignment_id,
                source_node_id=item.source_node_id,
                target_node_id=item.target_node_id,
                profile_id=item.profile_id,
                user_id=item.user_id,
            )
            for item in plan.items
        ),
    )


def _plan_from_read(payload: FailoverPlanRead) -> FailoverPlan:
    return FailoverPlan(
        source_node_id=payload.source_node_id,
        items=tuple(
            FailoverPlanItem(
                assignment_id=item.assignment_id,
                source_node_id=item.source_node_id,
                target_node_id=item.target_node_id,
                profile_id=item.profile_id,
                user_id=item.user_id,
            )
            for item in payload.items
        ),
        dry_run=payload.dry_run,
        plan_id=payload.plan_id,
    )


@router.post("/plan", response_model=FailoverPlanRead)
async def failover_plan(
    payload: FailoverPlanRequest,
    _admin: AdminUser,
    failover: FailoverServiceDep,
) -> FailoverPlanRead:
    plan = await failover.plan(
        payload.source_node_id,
        dry_run=payload.dry_run,
        policy=payload.policy,
    )
    return _plan_read(plan)


@router.post("/execute", response_model=FailoverResultRead)
async def failover_execute(
    payload: FailoverPlanRead,
    _admin: AdminUser,
    failover: FailoverServiceDep,
) -> FailoverResultRead:
    result = await failover.execute(_plan_from_read(payload))
    return FailoverResultRead(
        plan_id=result.plan_id,
        migrated=result.migrated,
        skipped=result.skipped,
        dry_run=result.dry_run,
    )
