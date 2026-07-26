from __future__ import annotations

import uuid

from app.agent.ip_limit import IpLimitService
from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.models import ProviderKind


async def _seed(app_state: AppState, *, device_limit: int | None) -> dict:
    ids: dict = {}
    async with app_state.db.session() as session:
        user = User(
            username=f"u-{uuid.uuid4().hex[:8]}",
            hashed_password=hash_password("strong-password-1234-AB!"),
            role=UserRole.USER,
            device_limit=device_limit,
        )
        session.add(user)
        await session.flush()
        ids["user_id"] = user.id
        node = Node(
            name=f"n-{uuid.uuid4().hex[:8]}",
            slug=f"n-{uuid.uuid4().hex[:8]}",
            host="10.0.0.1",
            port=443,
            max_users=100,
            node_metadata={},
            status=NodeStatus.ACTIVE,
        )
        session.add(node)
        await session.flush()
        profile = Profile(
            name="p",
            slug=f"p-{uuid.uuid4().hex[:8]}",
            provider_kind=ProviderKind.XRAY,
            node_id=node.id,
            protocol="vless",
            settings={},
        )
        session.add(profile)
        await session.flush()
        assignment = ClientAssignment(
            user_id=user.id,
            profile_id=profile.id,
            node_id=node.id,
            provider_kind=ProviderKind.XRAY,
            status=AssignmentStatus.ACTIVE,
        )
        session.add(assignment)
        await session.flush()
        ids["assignment_id"] = assignment.id
    return ids


async def _status(app_state: AppState, assignment_id: uuid.UUID) -> AssignmentStatus:
    async with app_state.db.session() as session:
        a = await session.get(ClientAssignment, assignment_id)
        return a.status


async def test_under_device_limit_stays_active(app_state: AppState):
    ids = await _seed(app_state, device_limit=3)
    svc = IpLimitService(app_state.db, app_state.cache)
    await svc.report([(ids["assignment_id"], ip) for ip in ("1.1.1.1", "2.2.2.2")])
    assert await _status(app_state, ids["assignment_id"]) is AssignmentStatus.ACTIVE


async def test_over_device_limit_disables(app_state: AppState):
    ids = await _seed(app_state, device_limit=2)
    svc = IpLimitService(app_state.db, app_state.cache)
    aid = ids["assignment_id"]
    await svc.report([(aid, "1.1.1.1"), (aid, "2.2.2.2"), (aid, "3.3.3.3")])
    assert await _status(app_state, aid) is AssignmentStatus.DISABLED


async def test_no_limit_never_disables(app_state: AppState):
    ids = await _seed(app_state, device_limit=None)
    svc = IpLimitService(app_state.db, app_state.cache)
    aid = ids["assignment_id"]
    await svc.report([(aid, f"{i}.{i}.{i}.{i}") for i in range(1, 9)])
    assert await _status(app_state, aid) is AssignmentStatus.ACTIVE


async def test_ip_limit_auto_recovers_when_devices_drop(app_state: AppState):
    from app.agent.ip_limit import _key

    ids = await _seed(app_state, device_limit=2)
    svc = IpLimitService(app_state.db, app_state.cache)
    aid = ids["assignment_id"]
    await svc.report([(aid, "1.1.1.1"), (aid, "2.2.2.2"), (aid, "3.3.3.3")])
    assert await _status(app_state, aid) is AssignmentStatus.DISABLED
    await app_state.cache.client.delete(_key(ids["user_id"]))
    await svc.report([(aid, "1.1.1.1")])
    assert await _status(app_state, aid) is AssignmentStatus.ACTIVE
