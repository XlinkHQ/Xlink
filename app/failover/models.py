from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FailoverPlanItem:
    assignment_id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    profile_id: uuid.UUID
    user_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class FailoverPlan:
    source_node_id: uuid.UUID
    items: tuple[FailoverPlanItem, ...]
    dry_run: bool = False
    plan_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass(frozen=True, slots=True)
class FailoverResult:
    plan_id: uuid.UUID
    migrated: int
    skipped: int
    dry_run: bool
