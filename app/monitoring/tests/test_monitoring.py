from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.security import hash_password
from app.db.session import Database
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.monitoring.exporters import PrometheusExporter
from app.monitoring.models import Metric, MetricsSnapshot
from app.monitoring.service import MonitoringService
from app.providers.base.models import ProviderKind
from app.providers.discovery import build_registry
from app.traffic.models import TrafficRecord


async def _seed(db: Database) -> None:
    async with db.session() as session:
        user = User(
            email="m@example.com",
            username="monitor",
            hashed_password=hash_password("strong-password-123456"),
            role=UserRole.USER,
            is_active=True,
        )
        active_node = Node(
            name="active",
            slug=f"active-{uuid.uuid4().hex[:8]}",
            host="active",
            port=443,
            status=NodeStatus.ACTIVE,
            max_users=10,
            current_users=1,
            node_metadata={"assignment_stats": {"a": {"used_bytes": 100}}},
        )
        offline_node = Node(
            name="offline",
            slug=f"offline-{uuid.uuid4().hex[:8]}",
            host="offline",
            port=443,
            status=NodeStatus.OFFLINE,
            max_users=10,
            current_users=0,
            node_metadata={},
        )
        session.add_all([user, active_node, offline_node])
        await session.flush()
        profile = Profile(
            name="profile",
            slug=f"profile-{uuid.uuid4().hex[:8]}",
            provider_kind=ProviderKind.XRAY,
            node_id=active_node.id,
            protocol="vless",
            settings={},
            is_active=True,
        )
        session.add(profile)
        await session.flush()
        assignment = ClientAssignment(
            user_id=user.id,
            profile_id=profile.id,
            node_id=active_node.id,
            provider_kind=ProviderKind.XRAY,
            status=AssignmentStatus.ACTIVE,
        )
        session.add(assignment)
        await session.flush()
        session.add(
            TrafficRecord(
                assignment_id=assignment.id,
                node_id=active_node.id,
                upload_bytes=60,
                download_bytes=40,
                total_bytes=100,
                collected_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )


async def test_metrics_collection_and_aggregation(db: Database) -> None:
    await _seed(db)
    service = MonitoringService(db.sessionmaker(), build_registry())

    snapshot = await service.snapshot()

    assert snapshot.get("active_users") == 1
    assert snapshot.get("active_nodes") == 1
    assert snapshot.get("offline_nodes") == 1
    assert snapshot.get("active_assignments") == 1
    assert snapshot.get("total_traffic_bytes") == 100


async def test_provider_and_node_health_metrics(db: Database) -> None:
    await _seed(db)
    service = MonitoringService(db.sessionmaker(), build_registry())

    snapshot = await service.snapshot()

    assert snapshot.get("provider_health", provider="xray", kind="xray") == 1
    assert snapshot.get("active_nodes") == 1


def test_prometheus_export() -> None:
    text = PrometheusExporter().export(
        MetricsSnapshot(
            metrics=(
                Metric("active_users", 2),
                Metric("provider_health", 1, {"provider": "xray"}),
            )
        )
    )

    assert "xlink_active_users 2" in text
    assert 'xlink_provider_health{provider="xray"} 1' in text


async def test_empty_state(db: Database) -> None:
    service = MonitoringService(db.sessionmaker(), build_registry())

    snapshot = await service.snapshot()

    assert snapshot.get("active_users") == 0
    assert snapshot.get("active_nodes") == 0
    assert snapshot.get("offline_nodes") == 0
