from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.agent.config_sync import ConfigSyncService
from app.agent.reconcile import _apply_data_resets
from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import DataResetStrategy, User, UserRole
from app.providers.base.models import ProviderKind


async def _seed(session, *, user_kwargs: dict, assignment_kwargs: dict | None = None):
    node = Node(
        name="n1",
        slug=f"n-{uuid.uuid4().hex[:8]}",
        host="1.2.3.4",
        port=443,
        status=NodeStatus.ACTIVE,
    )
    session.add(node)
    await session.flush()
    profile = Profile(
        name="p1",
        slug=f"p-{uuid.uuid4().hex[:8]}",
        provider_kind=ProviderKind.XRAY,
        node_id=node.id,
        protocol="vless",
        settings={},
    )
    user = User(
        username=f"u-{uuid.uuid4().hex[:8]}",
        hashed_password=hash_password("x"),
        role=UserRole.USER,
        **user_kwargs,
    )
    session.add_all([profile, user])
    await session.flush()
    akw = {"status": AssignmentStatus.ACTIVE, "credentials": {}, **(assignment_kwargs or {})}
    assignment = ClientAssignment(
        user_id=user.id,
        profile_id=profile.id,
        node_id=node.id,
        provider_kind=ProviderKind.XRAY,
        provider_client_id="cid",
        **akw,
    )
    session.add(assignment)
    await session.flush()
    return node, user, assignment


async def _client_count(session, node_id) -> int:
    config = await ConfigSyncService(session).desired_config(node_id)
    return config["client_count"]


async def test_active_user_is_served(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        node, _user, _a = await _seed(session, user_kwargs={"is_active": True})
        assert await _client_count(session, node.id) == 1


async def test_expired_user_excluded(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        past = datetime.now(UTC) - timedelta(days=1)
        node, _user, _a = await _seed(session, user_kwargs={"expire_at": past})
        assert await _client_count(session, node.id) == 0


async def test_disabled_user_excluded(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        node, _user, _a = await _seed(session, user_kwargs={"is_active": False})
        assert await _client_count(session, node.id) == 0


async def test_removed_user_excluded(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        node, _user, _a = await _seed(session, user_kwargs={"removed": True})
        assert await _client_count(session, node.id) == 0


async def test_over_limit_user_excluded(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        node, _user, _a = await _seed(
            session,
            user_kwargs={"data_limit_bytes": 1000, "users_data_usage": 2000},
        )
        assert await _client_count(session, node.id) == 0


async def test_under_limit_user_served(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        node, _user, _a = await _seed(
            session,
            user_kwargs={"data_limit_bytes": 1000, "users_data_usage": 100},
        )
        assert await _client_count(session, node.id) == 1


async def test_data_reset_reenables_and_zeroes(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        old = datetime.now(UTC) - timedelta(days=2)
        node, user, assignment = await _seed(
            session,
            user_kwargs={
                "data_limit_bytes": 1000,
                "users_data_usage": 5000,
                "data_reset_strategy": DataResetStrategy.DAY,
                "last_reset_at": old,
            },
            assignment_kwargs={"used_bytes": 5000, "status": AssignmentStatus.LIMITED},
        )
        assert await _client_count(session, node.id) == 0

        woke = await _apply_data_resets(session)
        assert node.id in woke

        await session.refresh(user)
        await session.refresh(assignment)
        assert user.users_data_usage == 0
        assert assignment.used_bytes == 0
        assert assignment.status == AssignmentStatus.ACTIVE
        assert await _client_count(session, node.id) == 1


async def test_data_reset_skips_disabled_user(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        old = datetime.now(UTC) - timedelta(days=2)
        node, _user, assignment = await _seed(
            session,
            user_kwargs={
                "is_active": False,
                "data_reset_strategy": DataResetStrategy.DAY,
                "last_reset_at": old,
            },
            assignment_kwargs={"used_bytes": 5000, "status": AssignmentStatus.DISABLED},
        )
        await _apply_data_resets(session)
        await session.refresh(assignment)
        assert assignment.status == AssignmentStatus.DISABLED


async def test_usage_recompute_enforces_from_accumulated_bytes(app_state: AppState) -> None:
    from app.traffic.service import TrafficService

    async with app_state.db.session() as session:
        node, user, assignment = await _seed(
            session,
            user_kwargs={"data_limit_bytes": 100, "users_data_usage": 0},
            assignment_kwargs={"used_bytes": 5000, "status": AssignmentStatus.ACTIVE},
        )
        assert await _client_count(session, node.id) == 1

        svc = TrafficService(session, cache=app_state.cache)
        await svc._check_limits({assignment.id: assignment}, {assignment.id: 1})

        await session.refresh(user)
        await session.refresh(assignment)
        assert user.users_data_usage == 5000
        assert assignment.status == AssignmentStatus.LIMITED
        assert await _client_count(session, node.id) == 0


async def test_manual_reset_reenables_and_wakes(app_state: AppState) -> None:
    from app.traffic.service import TrafficService

    async with app_state.db.session() as session:
        node, user, assignment = await _seed(
            session,
            user_kwargs={"data_limit_bytes": 1000, "users_data_usage": 5000},
            assignment_kwargs={"used_bytes": 5000, "status": AssignmentStatus.LIMITED},
        )
        assert await _client_count(session, node.id) == 0

        svc = TrafficService(session, cache=app_state.cache)
        await svc.reset_user(user.id)

        await session.refresh(user)
        await session.refresh(assignment)
        assert user.users_data_usage == 0
        assert assignment.status == AssignmentStatus.ACTIVE
        assert await _client_count(session, node.id) == 1


@pytest.mark.parametrize("strategy", [DataResetStrategy.DAY])
async def test_data_reset_respects_period(app_state: AppState, strategy) -> None:
    async with app_state.db.session() as session:
        recent = datetime.now(UTC) - timedelta(hours=1)
        node, _user, assignment = await _seed(
            session,
            user_kwargs={"data_reset_strategy": strategy, "last_reset_at": recent},
            assignment_kwargs={"used_bytes": 5000},
        )
        woke = await _apply_data_resets(session)
        assert woke == []
        await session.refresh(assignment)
        assert assignment.used_bytes == 5000
