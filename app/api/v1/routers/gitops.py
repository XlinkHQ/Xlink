from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.dependencies.auth import AdminUser
from app.dependencies.services import GitOpsServiceDep
from app.gitops.schemas import GitOpsRecordRead

router = APIRouter(prefix="/gitops", tags=["gitops"])


class SnapshotPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_type: str
    entity_id: uuid.UUID | None = None
    payload: dict[str, Any]


class CommitRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    before: SnapshotPayload | None = None
    after: SnapshotPayload
    actor: str | None = None
    message: str | None = None


class DiffRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    before: SnapshotPayload
    after: SnapshotPayload


class DiffResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    added: dict[str, Any]
    changed: dict[str, dict[str, Any]]
    removed: dict[str, Any]


@router.post("/commit", response_model=GitOpsRecordRead)
async def gitops_commit(
    payload: CommitRequest,
    _admin: AdminUser,
    gitops: GitOpsServiceDep,
) -> GitOpsRecordRead:
    before = (
        gitops.snapshot(
            entity_type=payload.before.entity_type,
            entity_id=payload.before.entity_id,
            payload=payload.before.payload,
        )
        if payload.before is not None
        else None
    )
    after = gitops.snapshot(
        entity_type=payload.after.entity_type,
        entity_id=payload.after.entity_id,
        payload=payload.after.payload,
    )
    record = await gitops.commit(
        before=before,
        after=after,
        actor=payload.actor,
        message=payload.message,
    )
    return GitOpsRecordRead.model_validate(record)


@router.post("/diff", response_model=DiffResponse)
async def gitops_diff(
    payload: DiffRequest,
    _admin: AdminUser,
    gitops: GitOpsServiceDep,
) -> DiffResponse:
    before = gitops.snapshot(
        entity_type=payload.before.entity_type,
        entity_id=payload.before.entity_id,
        payload=payload.before.payload,
    )
    after = gitops.snapshot(
        entity_type=payload.after.entity_type,
        entity_id=payload.after.entity_id,
        payload=payload.after.payload,
    )
    diff = gitops.diff(before, after)
    return DiffResponse(added=diff.added, changed=diff.changed, removed=diff.removed)
