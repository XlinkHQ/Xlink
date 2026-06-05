from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class SchedulerPolicyName(StrEnum):
    LEAST_LOADED = "least_loaded"
    CAPACITY_FIRST = "capacity_first"
    REGION_FIRST = "region_first"
    BALANCED = "balanced"
    CUSTOM_WEIGHTED = "custom_weighted"


@dataclass(frozen=True, slots=True)
class SchedulerRequest:
    profile_id: uuid.UUID
    preferred_region: str | None = None
    policy: SchedulerPolicyName = SchedulerPolicyName.BALANCED
    dry_run: bool = False
    weights: dict[str, float] | None = None


@dataclass(frozen=True, slots=True)
class NodeScore:
    node_id: uuid.UUID
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SchedulerDecision:
    node_id: uuid.UUID
    profile_id: uuid.UUID
    policy: SchedulerPolicyName
    dry_run: bool
    score: float
    candidates: tuple[NodeScore, ...]
