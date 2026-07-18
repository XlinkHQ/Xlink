from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.dependencies.auth import AdminUser, SudoAdminUser, WriteAdminUser
from app.dependencies.core import DatabaseDep, SettingsDep
from app.dependencies.services import (
    AdminServiceDep,
    AssignmentServiceDep,
    TrafficServiceDep,
    UserServiceDep,
)
from app.traffic.scheduler import run_retention
from app.traffic.schemas import TrafficTotals, TrafficUsage

router = APIRouter(prefix="/traffic", tags=["traffic"])


class RetentionRead(BaseModel):
    enabled: bool
    retention_days: int
    interval_seconds: int


class CleanupRequest(BaseModel):
    retention_days: int = Field(ge=1, le=3650)


class CleanupResult(BaseModel):
    deleted: int
    retention_days: int


class OnlineUsersRead(BaseModel):
    user_ids: list[str]
    window_seconds: int


@router.get("/summary", response_model=TrafficTotals)
async def traffic_summary(
    _admin: SudoAdminUser,
    traffic: TrafficServiceDep,
) -> TrafficTotals:
    return await traffic.totals()


@router.get("/online", response_model=OnlineUsersRead)
async def online_users(
    _admin: SudoAdminUser,
    traffic: TrafficServiceDep,
    window_seconds: int = 45,
) -> OnlineUsersRead:
    ids = await traffic.online_user_ids(window_seconds)
    return OnlineUsersRead(user_ids=[str(i) for i in ids], window_seconds=window_seconds)


@router.get("/assignments/{assignment_id}", response_model=TrafficUsage)
async def assignment_usage(
    assignment_id: uuid.UUID,
    admin: AdminUser,
    traffic: TrafficServiceDep,
    assignments: AssignmentServiceDep,
    users: UserServiceDep,
) -> TrafficUsage:
    assignment = await assignments.get(assignment_id)
    users.assert_can_manage(admin, await users.get(assignment.user_id))
    return await traffic.usage_for_assignment(assignment_id)


class NodeUsageRead(BaseModel):
    node_id: uuid.UUID
    total_bytes: int


class NodeUserUsageRead(BaseModel):
    user_id: uuid.UUID
    total_bytes: int


@router.get("/nodes", response_model=list[NodeUsageRead])
async def node_usage(_admin: SudoAdminUser, traffic: TrafficServiceDep) -> list[NodeUsageRead]:
    usage = await traffic.usage_by_node()
    return [NodeUsageRead(node_id=nid, total_bytes=b) for nid, b in usage.items()]


@router.get("/nodes/{node_id}/users", response_model=list[NodeUserUsageRead])
async def node_user_usage(
    node_id: uuid.UUID,
    _admin: SudoAdminUser,
    traffic: TrafficServiceDep,
) -> list[NodeUserUsageRead]:
    rows = await traffic.usage_by_node_user(node_id)
    return [NodeUserUsageRead(user_id=uid, total_bytes=b) for uid, b in rows]


class UserNodeUsageRead(BaseModel):
    node_id: uuid.UUID
    node_name: str
    total_bytes: int


@router.get("/users/{user_id}/nodes", response_model=list[UserNodeUsageRead])
async def user_node_usage(
    user_id: uuid.UUID,
    admin: AdminUser,
    traffic: TrafficServiceDep,
    users: UserServiceDep,
) -> list[UserNodeUsageRead]:
    users.assert_can_manage(admin, await users.get(user_id))
    rows = await traffic.usage_by_user_node(user_id)
    return [UserNodeUsageRead(node_id=nid, node_name=name, total_bytes=b) for nid, name, b in rows]


class NodeUsageSeriesPoint(BaseModel):
    ts: str
    upload_bytes: int
    download_bytes: int
    total_bytes: int


@router.get("/nodes/{node_id}/usage-series", response_model=list[NodeUsageSeriesPoint])
async def node_usage_series(
    node_id: uuid.UUID,
    _admin: SudoAdminUser,
    traffic: TrafficServiceDep,
    hours: int = 24,
) -> list[NodeUsageSeriesPoint]:
    rows = await traffic.usage_hourly_for_node(node_id, hours)
    return [
        NodeUsageSeriesPoint(ts=ts, upload_bytes=up, download_bytes=dn, total_bytes=up + dn)
        for ts, up, dn in rows
    ]


@router.get("/profiles/{profile_id}/usage-series", response_model=list[NodeUsageSeriesPoint])
async def profile_usage_series(
    profile_id: uuid.UUID,
    _admin: SudoAdminUser,
    traffic: TrafficServiceDep,
    hours: int = 24,
) -> list[NodeUsageSeriesPoint]:
    rows = await traffic.usage_hourly_for_profile(profile_id, hours)
    return [
        NodeUsageSeriesPoint(ts=ts, upload_bytes=up, download_bytes=dn, total_bytes=up + dn)
        for ts, up, dn in rows
    ]


class ProfileUsageTotal(BaseModel):
    total_bytes: int


@router.get("/profiles/{profile_id}/usage", response_model=ProfileUsageTotal)
async def profile_usage_total(
    profile_id: uuid.UUID,
    _admin: SudoAdminUser,
    traffic: TrafficServiceDep,
) -> ProfileUsageTotal:
    return ProfileUsageTotal(total_bytes=await traffic.usage_total_for_profile(profile_id))


class UsageSeriesPoint(BaseModel):
    date: str
    upload_bytes: int
    download_bytes: int
    total_bytes: int


@router.get("/users/{user_id}/usage-series", response_model=list[UsageSeriesPoint])
async def user_usage_series(
    user_id: uuid.UUID,
    admin: AdminUser,
    traffic: TrafficServiceDep,
    users: UserServiceDep,
    days: int = 14,
) -> list[UsageSeriesPoint]:
    users.assert_can_manage(admin, await users.get(user_id))
    rows = await traffic.usage_series_for_user(user_id, days)
    return [
        UsageSeriesPoint(date=d, upload_bytes=up, download_bytes=dn, total_bytes=up + dn)
        for d, up, dn in rows
    ]


class ResetUsageResult(BaseModel):
    reset_assignments: int


class UsageQuery(BaseModel):
    user_ids: list[uuid.UUID] = Field(max_length=500)


class UserUsage(BaseModel):
    user_id: uuid.UUID
    used_bytes: int
    limit_bytes: int
    unlimited: bool


@router.post("/users/usage", response_model=list[UserUsage])
async def users_usage(
    payload: UsageQuery,
    admin: AdminUser,
    traffic: TrafficServiceDep,
    users: AdminServiceDep,
) -> list[UserUsage]:
    await users.assert_can_manage_many(admin, payload.user_ids, skip_missing=True)
    usage = await traffic.usage_for_users(payload.user_ids)
    return [
        UserUsage(user_id=uid, used_bytes=used, limit_bytes=limit, unlimited=unlimited)
        for uid, (used, limit, unlimited) in usage.items()
    ]


class UserLastSeen(BaseModel):
    user_id: uuid.UUID
    last_seen_at: datetime


@router.post("/users/last-seen", response_model=list[UserLastSeen])
async def users_last_seen(
    payload: UsageQuery,
    admin: AdminUser,
    traffic: TrafficServiceDep,
    users: AdminServiceDep,
) -> list[UserLastSeen]:
    await users.assert_can_manage_many(admin, payload.user_ids, skip_missing=True)
    seen = await traffic.last_seen_for_users(payload.user_ids)
    return [UserLastSeen(user_id=uid, last_seen_at=ts) for uid, ts in seen.items()]


@router.post("/users/{user_id}/reset", response_model=ResetUsageResult)
async def reset_user_usage(
    user_id: uuid.UUID,
    admin: WriteAdminUser,
    traffic: TrafficServiceDep,
    users: UserServiceDep,
) -> ResetUsageResult:
    users.assert_can_manage(admin, await users.get(user_id))
    count = await traffic.reset_user(user_id)
    await users.notify_data_reset(user_id)
    return ResetUsageResult(reset_assignments=count)


@router.get("/retention", response_model=RetentionRead)
async def traffic_retention(_admin: SudoAdminUser, settings: SettingsDep) -> RetentionRead:
    return RetentionRead(
        enabled=settings.traffic_retention_enabled,
        retention_days=settings.traffic_retention_days,
        interval_seconds=settings.traffic_retention_interval_seconds,
    )


@router.post("/cleanup", response_model=CleanupResult)
async def traffic_cleanup(
    payload: CleanupRequest,
    _admin: SudoAdminUser,
    db: DatabaseDep,
) -> CleanupResult:
    deleted = await run_retention(db, retention_days=payload.retention_days)
    return CleanupResult(deleted=deleted, retention_days=payload.retention_days)
