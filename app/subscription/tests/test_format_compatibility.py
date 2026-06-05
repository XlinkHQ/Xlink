from __future__ import annotations

import json
import uuid

import yaml

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.models import ProviderKind
from app.subscription.generator import SubscriptionGenerator
from app.subscription.renderer import SubscriptionRenderer
from app.subscription.repository import SubscriptionRepository
from app.subscription.schemas import FeedRequest, FeedScope, SubscriptionFormat
from app.subscription.service import SubscriptionService


async def _service(app_state: AppState) -> SubscriptionService:
    session = app_state.db.sessionmaker()
    return SubscriptionService(
        SubscriptionRepository(session),
        SubscriptionGenerator(app_state.providers),
        SubscriptionRenderer(),
        app_state.cache,
    )


async def _seed(app_state: AppState, *, protocol="vless", settings=None) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    async with app_state.db.session() as session:
        user = User(
            email=f"u-{uuid.uuid4().hex[:8]}@x.io",
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
            protocol=protocol,
            settings=settings or {"security": "tls", "sni": "x.io"},
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
        ids.update(
            user_id=user.id, node_id=node.id, profile_id=profile.id, assignment_id=assignment.id
        )
    return ids


async def test_assignment_compatibility_singbox(app_state: AppState):
    ids = await _seed(app_state, protocol="vless")
    service = await _service(app_state)
    feed = await service.feed(
        FeedRequest(
            scope=FeedScope.ASSIGNMENT,
            subject_id=ids["assignment_id"],
            format=SubscriptionFormat.SINGBOX_JSON,
            use_cache=False,
        )
    )
    doc = json.loads(feed.content)
    assert doc["outbounds"][0]["type"] == "vless"


async def test_profile_compatibility_clash(app_state: AppState):
    ids = await _seed(app_state, protocol="trojan")
    service = await _service(app_state)
    feed = await service.feed(
        FeedRequest(
            scope=FeedScope.PROFILE,
            subject_id=ids["profile_id"],
            format=SubscriptionFormat.CLASH_YAML,
            use_cache=False,
        )
    )
    doc = yaml.safe_load(feed.content)
    assert doc["proxies"][0]["type"] == "trojan"


async def test_user_compatibility_mihomo(app_state: AppState):
    ids = await _seed(app_state, protocol="vmess")
    service = await _service(app_state)
    feed = await service.feed(
        FeedRequest(
            scope=FeedScope.USER,
            subject_id=ids["user_id"],
            format=SubscriptionFormat.MIHOMO_YAML,
            use_cache=False,
        )
    )
    doc = yaml.safe_load(feed.content)
    assert doc["proxies"][0]["type"] == "vmess"


async def test_provider_compatibility_vless_uri(app_state: AppState):
    ids = await _seed(app_state, protocol="vless")
    service = await _service(app_state)
    feed = await service.feed(
        FeedRequest(
            scope=FeedScope.USER,
            subject_id=ids["user_id"],
            format=SubscriptionFormat.VLESS_URI,
            use_cache=False,
        )
    )
    assert feed.content.startswith("vless://")


async def test_engine_compatibility_all_container_formats(app_state: AppState):
    ids = await _seed(app_state, protocol="vless")
    service = await _service(app_state)
    for fmt in (
        SubscriptionFormat.TEXT,
        SubscriptionFormat.BASE64,
        SubscriptionFormat.SINGBOX_JSON,
        SubscriptionFormat.CLASH_YAML,
        SubscriptionFormat.MIHOMO_YAML,
        SubscriptionFormat.VLESS_URI,
    ):
        feed = await service.feed(
            FeedRequest(
                scope=FeedScope.USER,
                subject_id=ids["user_id"],
                format=fmt,
                use_cache=False,
            )
        )
        assert feed.content
        assert len(feed.content_hash) == 64
        assert feed.items[0].uri.startswith("vless://")


async def test_engine_caches_per_format(app_state: AppState):
    ids = await _seed(app_state, protocol="vless")
    service = await _service(app_state)
    text = await service.feed(
        FeedRequest(
            scope=FeedScope.USER,
            subject_id=ids["user_id"],
            format=SubscriptionFormat.TEXT,
        )
    )
    singbox = await service.feed(
        FeedRequest(
            scope=FeedScope.USER,
            subject_id=ids["user_id"],
            format=SubscriptionFormat.SINGBOX_JSON,
        )
    )
    assert text.content != singbox.content
