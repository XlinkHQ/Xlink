from __future__ import annotations

import uuid

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.inbound_host import InboundHost
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.models import ProviderKind
from app.subscription.generator import SubscriptionGenerator
from app.subscription.renderer import SubscriptionRenderer
from app.subscription.repository import SubscriptionRepository
from app.subscription.service import SubscriptionService


async def _service(app_state: AppState) -> SubscriptionService:
    return SubscriptionService(
        SubscriptionRepository(app_state.db.sessionmaker()),
        SubscriptionGenerator(app_state.providers),
        SubscriptionRenderer(),
        app_state.cache,
    )


async def _seed(app_state: AppState) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    async with app_state.db.session() as session:
        user = User(
            username=f"u{uuid.uuid4().hex[:8]}",
            hashed_password=hash_password("strong-password-123456"),
            role=UserRole.USER,
        )
        session.add(user)
        await session.flush()
        node = Node(
            name=f"node-{uuid.uuid4().hex[:8]}",
            slug=f"node-{uuid.uuid4().hex[:8]}",
            host="203.0.113.10",
            port=443,
            max_users=100,
            current_users=0,
            node_metadata={},
            status=NodeStatus.ACTIVE,
        )
        session.add(node)
        await session.flush()
        profile = Profile(
            name=f"profile-{uuid.uuid4().hex[:8]}",
            slug=f"profile-{uuid.uuid4().hex[:8]}",
            provider_kind=ProviderKind.XRAY,
            node_id=node.id,
            protocol="vless",
            settings={"security": "tls"},
            is_active=True,
        )
        session.add(profile)
        await session.flush()
        assignment = ClientAssignment(
            user_id=user.id,
            profile_id=profile.id,
            node_id=node.id,
            provider_kind=ProviderKind.XRAY,
            provider_client_id=str(uuid.uuid4()),
            status=AssignmentStatus.ACTIVE,
        )
        session.add(assignment)
        await session.flush()
        ids.update(user_id=user.id, profile_id=profile.id)
    return ids


async def _add_host(app_state: AppState, **kwargs) -> None:
    async with app_state.db.session() as session:
        session.add(InboundHost(**kwargs))


async def test_no_hosts_yields_single_config(app_state: AppState) -> None:
    ids = await _seed(app_state)
    feed = await (await _service(app_state)).user_feed(ids["user_id"], use_cache=False)
    assert len(feed.items) == 1
    assert "203.0.113.10" in feed.items[0].uri


async def test_inbound_host_overrides_address_and_remark(app_state: AppState) -> None:
    ids = await _seed(app_state)
    await _add_host(
        app_state,
        profile_id=ids["profile_id"],
        remark="CDN-Frankfurt",
        address="cdn.example.com",
        sni="cdn.example.com",
        weight=10,
    )
    feed = await (await _service(app_state)).user_feed(ids["user_id"], use_cache=False)
    assert len(feed.items) == 1
    uri = feed.items[0].uri
    assert "cdn.example.com" in uri
    assert "CDN-Frankfurt" in uri
    assert "203.0.113.10" not in uri


async def test_two_hosts_yield_two_configs_ordered_by_weight(app_state: AppState) -> None:
    ids = await _seed(app_state)
    await _add_host(
        app_state, profile_id=ids["profile_id"], remark="low", address="low.example.com", weight=1
    )
    await _add_host(
        app_state,
        profile_id=ids["profile_id"],
        remark="high",
        address="high.example.com",
        weight=99,
    )
    feed = await (await _service(app_state)).user_feed(ids["user_id"], use_cache=False)
    assert len(feed.items) == 2

    assert "high.example.com" in feed.items[0].uri
    assert "low.example.com" in feed.items[1].uri


async def test_universal_host_applies_to_every_inbound(app_state: AppState) -> None:
    ids = await _seed(app_state)
    await _add_host(
        app_state,
        profile_id=None,
        is_universal=True,
        remark="Universal",
        address="universal.example.com",
        weight=5,
    )
    feed = await (await _service(app_state)).user_feed(ids["user_id"], use_cache=False)
    assert len(feed.items) == 1
    assert "universal.example.com" in feed.items[0].uri


async def test_disabled_host_is_skipped(app_state: AppState) -> None:
    ids = await _seed(app_state)
    await _add_host(
        app_state,
        profile_id=ids["profile_id"],
        remark="off",
        address="off.example.com",
        is_disabled=True,
    )
    feed = await (await _service(app_state)).user_feed(ids["user_id"], use_cache=False)

    assert len(feed.items) == 1
    assert "203.0.113.10" in feed.items[0].uri
