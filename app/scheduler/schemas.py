from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.scheduler.models import SchedulerPolicyName


class SchedulerRequestSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_id: uuid.UUID
    preferred_region: str | None = None
    policy: SchedulerPolicyName = SchedulerPolicyName.BALANCED
    dry_run: bool = False
    weights: dict[str, float] | None = None

    @model_validator(mode="after")
    def _require_weights_for_custom(self) -> SchedulerRequestSchema:
        if self.policy == SchedulerPolicyName.CUSTOM_WEIGHTED and self.weights is None:
            raise ValueError("weights required for CUSTOM_WEIGHTED policy")
        return self


class NodeScoreRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: uuid.UUID
    score: float
    reasons: tuple[str, ...]


class SchedulerDecisionRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: uuid.UUID
    profile_id: uuid.UUID
    policy: SchedulerPolicyName
    dry_run: bool
    score: float
    candidates: tuple[NodeScoreRead, ...] = Field(default_factory=tuple)
