from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.dependencies.auth import AdminUser, SudoAdminUser
from app.dependencies.services import GitOpsServiceDep
from app.gitops.schemas import (
    CommitRequest,
    DiffRequest,
    DiffResponse,
    GitOpsRecordRead,
    SnapshotPayload,
)

router = APIRouter(prefix="/gitops", tags=["gitops"])


def _assert_same_entity(before: SnapshotPayload, after: SnapshotPayload) -> None:
    if before.entity_type != after.entity_type or before.entity_id != after.entity_id:
        raise HTTPException(
            status_code=400,
            detail="before and after snapshots must refer to the same entity",
        )


def _to_snapshot(gitops: GitOpsServiceDep, payload: SnapshotPayload):
    return gitops.snapshot(
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        payload=payload.payload,
    )


@router.post("/commit", response_model=GitOpsRecordRead)
async def gitops_commit(
    payload: CommitRequest,
    _admin: SudoAdminUser,
    gitops: GitOpsServiceDep,
) -> GitOpsRecordRead:
    if payload.before is not None:
        _assert_same_entity(payload.before, payload.after)
    before = _to_snapshot(gitops, payload.before) if payload.before is not None else None
    after = _to_snapshot(gitops, payload.after)
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
    _assert_same_entity(payload.before, payload.after)
    before = _to_snapshot(gitops, payload.before)
    after = _to_snapshot(gitops, payload.after)
    diff = gitops.diff(before, after)
    return DiffResponse(added=diff.added, changed=diff.changed, removed=diff.removed)


@router.get("/records", response_model=list[GitOpsRecordRead])
async def gitops_records(
    _admin: AdminUser,
    gitops: GitOpsServiceDep,
    limit: int = 100,
) -> list[GitOpsRecordRead]:
    records = await gitops.list_recent(limit=min(max(limit, 1), 500))
    return [GitOpsRecordRead.model_validate(r) for r in records]
