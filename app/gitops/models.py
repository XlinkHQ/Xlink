from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class GitSnapshot:
    entity_type: str
    entity_id: uuid.UUID | None
    data: dict[str, Any]
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class GitDiff:
    added: dict[str, Any]
    changed: dict[str, dict[str, Any]]
    removed: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    entity_type: str
    entity_id: uuid.UUID | None
    restore_to: dict[str, Any]
    reverse_diff: GitDiff
