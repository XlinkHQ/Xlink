from __future__ import annotations

import math
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.scheduler.models import SchedulerPolicyName

_WEIGHT_KEYS = {"load", "capacity", "region", "traffic"}


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
        if self.weights is not None:
            # Reject junk that would invert or collapse scoring: unknown keys,
            # negative/NaN/inf values, or an all-zero set (→ selection would fall
            # to the tie-breaker and silently ignore load/capacity).
            bad = set(self.weights) - _WEIGHT_KEYS
            if bad:
                raise ValueError(f"unknown weight keys: {sorted(bad)}")
            for k, v in self.weights.items():
                if not math.isfinite(v) or v < 0:
                    raise ValueError(f"weight '{k}' must be a finite value >= 0")
            if sum(self.weights.values()) <= 0:
                raise ValueError("weights must not all be zero")
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
