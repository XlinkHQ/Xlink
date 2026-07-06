from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.scheduler.models import SchedulerPolicyName


class FailoverPlanRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_node_id: uuid.UUID
    dry_run: bool = False
    policy: SchedulerPolicyName = SchedulerPolicyName.BALANCED


class FailoverPlanItemRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    assignment_id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    profile_id: uuid.UUID
    user_id: uuid.UUID


class FailoverPlanRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_id: uuid.UUID
    source_node_id: uuid.UUID
    dry_run: bool
    items: tuple[FailoverPlanItemRead, ...]


class FailoverResultRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_id: uuid.UUID
    migrated: int
    skipped: int
    dry_run: bool
