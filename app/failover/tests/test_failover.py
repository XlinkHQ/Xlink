from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.events.models import SubscriptionGenerated
from app.failover.service import FailoverService
from app.providers.base.exceptions import ProviderError
from app.providers.base.models import ClientResult, ClientSpec, ProviderKind
from app.providers.xray.provider import XrayProvider


async def _seed(app_state: AppState, *, active: bool = True):
    async with app_state.db.session() as session:
        user = User(
            email=f"fail-{uuid.uuid4().hex[:8]}@example.com",
            username=f"fail{uuid.uuid4().hex[:8]}",
            hashed_password=hash_password("strong-password-123456"),
            role=UserRole.USER,
        )
        old_node = Node(
            name="old",
            slug=f"old-{uuid.uuid4().hex[:8]}",
            host="old",
            port=443,
            status=NodeStatus.OFFLINE,
            max_users=100,
            current_users=10,
            node_metadata={"provider_kinds": ["xray"]},
        )
        new_node = Node(
            name="new",
            slug=f"new-{uuid.uuid4().hex[:8]}",
            host="new",
            port=443,
            status=NodeStatus.ACTIVE,
            max_users=100,
            current_users=0,
            node_metadata={"provider_kinds": ["xray"]},
        )
        session.add_all([user, old_node, new_node])
        await session.flush()
        profile = Profile(
            name="profile",
            slug=f"profile-{uuid.uuid4().hex[:8]}",
            provider_kind=ProviderKind.XRAY,
            node_id=new_node.id,
            protocol="trojan",
            settings={},
            is_active=True,
        )
        session.add(profile)
        await session.flush()
        assignment = ClientAssignment(
            user_id=user.id,
            profile_id=profile.id,
            node_id=old_node.id,
            provider_kind=ProviderKind.XRAY,
            provider_client_id=str(uuid.uuid4()),
            status=AssignmentStatus.ACTIVE if active else AssignmentStatus.DISABLED,
        )
        session.add(assignment)
        await session.flush()
        return old_node.id, new_node.id, assignment.id, user.id


async def _service(app_state: AppState) -> FailoverService:
    return FailoverService(app_state.db, app_state.providers, app_state.events)


async def test_creates_failover_plan(app_state: AppState) -> None:
    old_node_id, new_node_id, assignment_id, _ = await _seed(app_state)
    service = await _service(app_state)

    plan = await service.plan(old_node_id)

    assert len(plan.items) == 1
    assert plan.items[0].assignment_id == assignment_id
    assert plan.items[0].target_node_id == new_node_id


async def test_migrates_assignment_and_emits_subscription_event(app_state: AppState) -> None:
    seen: list[SubscriptionGenerated] = []

    async def handler(event):
        seen.append(event)

    app_state.events.subscribe(SubscriptionGenerated, handler)
    old_node_id, new_node_id, assignment_id, user_id = await _seed(app_state)
    service = await _service(app_state)

    result = await service.failover_node(old_node_id)

    assert result.migrated == 1
    async with app_state.db.session() as session:
        old_assignment = await session.get(ClientAssignment, assignment_id)
        assert old_assignment is not None
        assert old_assignment.status is AssignmentStatus.DISABLED
        new_assignment = await session.scalar(
            select(ClientAssignment).where(
                ClientAssignment.user_id == user_id,
                ClientAssignment.node_id == new_node_id,
            )
        )
        assert new_assignment is not None
        assert new_assignment.status is AssignmentStatus.ACTIVE
    assert seen and seen[0].subject_id == user_id


async def test_skips_inactive_assignments(app_state: AppState) -> None:
    old_node_id, _, _, _ = await _seed(app_state, active=False)
    service = await _service(app_state)

    plan = await service.plan(old_node_id)

    assert plan.items == ()


async def test_rollback_on_provider_failure(app_state: AppState) -> None:
    class FailingProvider(XrayProvider):
        async def create_client(self, spec: ClientSpec) -> ClientResult:
            raise ProviderError("boom", code="provider_failed")

    app_state.providers.register(FailingProvider(), replace=True)
    old_node_id, new_node_id, assignment_id, _ = await _seed(app_state)
    service = await _service(app_state)

    result = await service.failover_node(old_node_id)

    assert result.migrated == 0
    assert result.skipped == 1
    async with app_state.db.session() as session:
        old_assignment = await session.get(ClientAssignment, assignment_id)
        assert old_assignment is not None
        assert old_assignment.status is AssignmentStatus.ACTIVE
        migrated = await session.scalar(
            select(ClientAssignment.id).where(ClientAssignment.node_id == new_node_id)
        )
        assert migrated is None


async def test_dry_run_does_not_mutate_data(app_state: AppState) -> None:
    old_node_id, new_node_id, assignment_id, _ = await _seed(app_state)
    service = await _service(app_state)

    result = await service.failover_node(old_node_id, dry_run=True)

    assert result.dry_run is True
    async with app_state.db.session() as session:
        old_assignment = await session.get(ClientAssignment, assignment_id)
        assert old_assignment is not None
        assert old_assignment.status is AssignmentStatus.ACTIVE
        migrated = await session.scalar(
            select(ClientAssignment.id).where(ClientAssignment.node_id == new_node_id)
        )
        assert migrated is None


async def test_idempotent_repeated_execution(app_state: AppState) -> None:
    old_node_id, _, _, _ = await _seed(app_state)
    service = await _service(app_state)
    plan = await service.plan(old_node_id)

    first = await service.execute(plan)
    second = await service.execute(plan)

    assert first.migrated == 1
    assert second.migrated == 0
    assert second.skipped == 1
