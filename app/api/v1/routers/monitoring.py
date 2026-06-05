from __future__ import annotations

from fastapi import APIRouter, Response

from app.dependencies.auth import AdminUser
from app.dependencies.services import MonitoringServiceDep
from app.monitoring.schemas import MetricRead, MetricsSnapshotRead

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _snapshot_read(snapshot) -> MetricsSnapshotRead:
    return MetricsSnapshotRead(
        metrics=tuple(
            MetricRead(name=m.name, value=m.value, labels=dict(m.labels)) for m in snapshot.metrics
        ),
        collected_at=snapshot.collected_at,
    )


@router.get("/summary", response_model=MetricsSnapshotRead)
async def monitoring_summary(
    _admin: AdminUser,
    monitoring: MonitoringServiceDep,
) -> MetricsSnapshotRead:
    return _snapshot_read(await monitoring.snapshot())


@router.get("/metrics", response_model=MetricsSnapshotRead)
async def monitoring_metrics(
    _admin: AdminUser,
    monitoring: MonitoringServiceDep,
) -> MetricsSnapshotRead:
    return _snapshot_read(await monitoring.snapshot())


@router.get("/prometheus", response_class=Response)
async def monitoring_prometheus(
    _admin: AdminUser,
    monitoring: MonitoringServiceDep,
) -> Response:
    body = await monitoring.prometheus()
    return Response(content=body, media_type="text/plain; version=0.0.4")
