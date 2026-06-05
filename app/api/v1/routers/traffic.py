from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.dependencies.auth import AdminUser
from app.dependencies.services import TrafficServiceDep
from app.traffic.schemas import TrafficTotals, TrafficUsage

router = APIRouter(prefix="/traffic", tags=["traffic"])


@router.get("/summary", response_model=TrafficTotals)
async def traffic_summary(
    _admin: AdminUser,
    traffic: TrafficServiceDep,
) -> TrafficTotals:
    return await traffic.totals()


@router.get("/assignments/{assignment_id}", response_model=TrafficUsage)
async def assignment_usage(
    assignment_id: uuid.UUID,
    _admin: AdminUser,
    traffic: TrafficServiceDep,
) -> TrafficUsage:
    return await traffic.usage_for_assignment(assignment_id)
