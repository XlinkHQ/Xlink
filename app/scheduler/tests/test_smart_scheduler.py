from __future__ import annotations

import uuid

import pytest

from app.db.session import Database
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.providers.base.models import ProviderKind
from app.providers.discovery import build_registry
from app.scheduler.models import SchedulerPolicyName, SchedulerRequest
from app.scheduler.service import SmartSchedulerService


async def _seed(db: Database, *, provider_kind: ProviderKind = ProviderKind.XRAY):
    async with db.session() as session:
        profile = Profile(
            name="profile",
            slug=f"profile-{uuid.uuid4().hex[:8]}",
            provider_kind=provider_kind,
            node_id=uuid.uuid4(),
            protocol="vless",
            settings={},
            is_active=True,
        )
        session.add(profile)
        nodes = [
            Node(
                name="n1",
                slug=f"n1-{uuid.uuid4().hex[:8]}",
                host="10.0.0.1",
                port=443,
                status=NodeStatus.ACTIVE,
                max_users=100,
                current_users=80,
                node_metadata={"region": "eu", "traffic_load": 0.2, "provider_kinds": ["xray"]},
            ),
            Node(
                name="n2",
                slug=f"n2-{uuid.uuid4().hex[:8]}",
                host="10.0.0.2",
                port=443,
                status=NodeStatus.ACTIVE,
                max_users=100,
                current_users=10,
                node_metadata={"region": "us", "traffic_load": 0.2, "provider_kinds": ["xray"]},
            ),
            Node(
                name="n3",
                slug=f"n3-{uuid.uuid4().hex[:8]}",
                host="10.0.0.3",
                port=443,
                status=NodeStatus.OFFLINE,
                max_users=100,
                current_users=0,
                node_metadata={"region": "eu", "provider_kinds": ["xray"]},
            ),
            Node(
                name="n4",
                slug=f"n4-{uuid.uuid4().hex[:8]}",
                host="10.0.0.4",
                port=443,
                status=NodeStatus.DISABLED,
                max_users=100,
                current_users=0,
                node_metadata={"region": "eu", "provider_kinds": ["xray"]},
            ),
            Node(
                name="n5",
                slug=f"n5-{uuid.uuid4().hex[:8]}",
                host="10.0.0.5",
                port=443,
                status=NodeStatus.ACTIVE,
                max_users=10,
                current_users=10,
                node_metadata={"region": "eu", "provider_kinds": ["xray"]},
            ),
        ]
        session.add_all(nodes)
        await session.flush()
        return profile.id, [node.id for node in nodes]


async def _scheduler(db: Database) -> SmartSchedulerService:
    return SmartSchedulerService(db.sessionmaker(), build_registry())


async def test_chooses_least_loaded_node(db: Database) -> None:
    profile_id, node_ids = await _seed(db)
    scheduler = await _scheduler(db)

    decision = await scheduler.choose_node(
        SchedulerRequest(profile_id=profile_id, policy=SchedulerPolicyName.LEAST_LOADED)
    )

    assert decision.node_id == node_ids[1]


async def test_excludes_offline_disabled_and_overloaded_nodes(db: Database) -> None:
    profile_id, node_ids = await _seed(db)
    scheduler = await _scheduler(db)

    decision = await scheduler.choose_node(
        SchedulerRequest(profile_id=profile_id, policy=SchedulerPolicyName.BALANCED)
    )
    candidate_ids = {candidate.node_id for candidate in decision.candidates}

    assert node_ids[2] not in candidate_ids
    assert node_ids[3] not in candidate_ids
    assert node_ids[4] not in candidate_ids


async def test_region_preference(db: Database) -> None:
    profile_id, node_ids = await _seed(db)
    scheduler = await _scheduler(db)

    decision = await scheduler.choose_node(
        SchedulerRequest(
            profile_id=profile_id,
            preferred_region="eu",
            policy=SchedulerPolicyName.REGION_FIRST,
        )
    )

    assert decision.node_id == node_ids[0]


async def test_provider_compatibility(db: Database) -> None:
    profile_id, _ = await _seed(db, provider_kind=ProviderKind.SING_BOX)
    scheduler = await _scheduler(db)

    with pytest.raises(Exception) as exc_info:
        await scheduler.choose_node(SchedulerRequest(profile_id=profile_id))

    assert getattr(exc_info.value, "code", "") in {
        "scheduler_provider_unavailable",
        "scheduler_no_node",
    }


async def test_deterministic_tie_breaking(db: Database) -> None:
    async with db.session() as session:
        profile = Profile(
            name="profile",
            slug=f"profile-{uuid.uuid4().hex[:8]}",
            provider_kind=ProviderKind.XRAY,
            node_id=uuid.uuid4(),
            protocol="vless",
            settings={},
            is_active=True,
        )
        a = Node(
            name="a",
            slug=f"a-{uuid.uuid4().hex[:8]}",
            host="a",
            port=443,
            status=NodeStatus.ACTIVE,
            max_users=100,
            current_users=10,
            node_metadata={},
        )
        b = Node(
            name="b",
            slug=f"b-{uuid.uuid4().hex[:8]}",
            host="b",
            port=443,
            status=NodeStatus.ACTIVE,
            max_users=100,
            current_users=10,
            node_metadata={},
        )
        session.add_all([profile, a, b])
        await session.flush()
        profile_id = profile.id
        expected_id = min(a.id, b.id, key=str)

    scheduler = await _scheduler(db)
    decision = await scheduler.choose_node(
        SchedulerRequest(profile_id=profile_id, policy=SchedulerPolicyName.LEAST_LOADED)
    )

    assert decision.node_id == expected_id


async def test_dry_run_result(db: Database) -> None:
    profile_id, _ = await _seed(db)
    scheduler = await _scheduler(db)

    decision = await scheduler.choose_node(SchedulerRequest(profile_id=profile_id, dry_run=True))

    assert decision.dry_run is True
    assert decision.candidates
