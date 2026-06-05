from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ValidationError
from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.models import ProviderKind
from app.providers.base.registry import ProviderRegistry
from app.subscription.generator import SubscriptionGenerator
from app.subscription.models import ProviderConfig
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


async def _seed(
    app_state: AppState,
    *,
    protocol: str = "vless",
    assignment_status: AssignmentStatus = AssignmentStatus.ACTIVE,
    profile_active: bool = True,
    node_status: NodeStatus = NodeStatus.ACTIVE,
    expires_at: datetime | None = None,
    provider_kind: ProviderKind = ProviderKind.XRAY,
    profile_provider_kind: ProviderKind | None = None,
) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    async with app_state.db.session() as session:
        user = User(
            email=f"u-{uuid.uuid4().hex[:8]}@example.com",
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
            status=node_status,
        )
        session.add(node)
        await session.flush()
        profile = Profile(
            name=f"profile-{uuid.uuid4().hex[:8]}",
            slug=f"profile-{uuid.uuid4().hex[:8]}",
            provider_kind=profile_provider_kind or provider_kind,
            node_id=node.id,
            protocol=protocol,
            settings={"flow": "xtls-rprx-vision", "security": "tls"},
            is_active=profile_active,
        )
        session.add(profile)
        await session.flush()
        assignment = ClientAssignment(
            user_id=user.id,
            profile_id=profile.id,
            node_id=node.id,
            provider_kind=provider_kind,
            provider_client_id=str(uuid.uuid4()),
            status=assignment_status,
            expires_at=expires_at,
        )
        session.add(assignment)
        await session.flush()
        ids.update(
            user_id=user.id,
            node_id=node.id,
            profile_id=profile.id,
            assignment_id=assignment.id,
        )
    return ids


async def test_generate_single_config(app_state: AppState) -> None:
    ids = await _seed(app_state)
    service = await _service(app_state)

    config = await service.generate_config(ids["assignment_id"])

    assert config.provider == "xray"
    assert config.protocol == "vless"
    assert config.uri.startswith("vless://")
    assert "203.0.113.10:443" in config.uri


async def test_generate_assignment_profile_and_user_feeds(app_state: AppState) -> None:
    ids = await _seed(app_state, protocol="trojan")
    service = await _service(app_state)

    assignment_feed = await service.assignment_feed(ids["assignment_id"], use_cache=False)
    profile_feed = await service.profile_feed(ids["profile_id"], use_cache=False)
    user_feed = await service.user_feed(ids["user_id"], use_cache=False)

    assert assignment_feed.items[0].uri.startswith("trojan://")
    assert profile_feed.content == assignment_feed.content
    assert user_feed.content == assignment_feed.content
    assert assignment_feed.etag == f'"{assignment_feed.content_hash}"'


async def test_feed_versioning_and_base64_format(app_state: AppState) -> None:
    ids = await _seed(app_state, protocol="vmess")
    service = await _service(app_state)

    text = await service.feed(
        FeedRequest(
            scope=FeedScope.USER,
            subject_id=ids["user_id"],
            format=SubscriptionFormat.TEXT,
            use_cache=False,
        )
    )
    encoded = await service.feed(
        FeedRequest(
            scope=FeedScope.USER,
            subject_id=ids["user_id"],
            format=SubscriptionFormat.BASE64,
            use_cache=False,
        )
    )

    assert text.version == "v1"
    assert encoded.version == "v1"
    assert text.content != encoded.content
    assert text.items[0].uri.startswith("vmess://")


async def test_feed_cache(app_state: AppState) -> None:
    ids = await _seed(app_state)
    service = await _service(app_state)

    cached = await service.user_feed(ids["user_id"], use_cache=True)
    async with app_state.db.session() as session:
        assignment = await session.get(ClientAssignment, ids["assignment_id"])
        assert assignment is not None
        assignment.status = AssignmentStatus.DISABLED

    still_cached = await service.user_feed(ids["user_id"], use_cache=True)
    fresh = await service.user_feed(ids["user_id"], use_cache=False)

    assert still_cached.content == cached.content
    assert fresh.content == ""
    assert fresh.items == ()


async def test_expiration_handling(app_state: AppState) -> None:
    ids = await _seed(app_state, expires_at=datetime.now(UTC) - timedelta(minutes=1))
    service = await _service(app_state)

    feed = await service.user_feed(ids["user_id"], use_cache=False)

    assert feed.content == ""
    assert feed.items == ()


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"assignment_status": AssignmentStatus.DISABLED}, "subscription_assignment_disabled"),
        ({"profile_active": False}, "subscription_profile_disabled"),
        ({"node_status": NodeStatus.DISABLED}, "subscription_node_disabled"),
        (
            {"provider_kind": ProviderKind.XRAY, "profile_provider_kind": ProviderKind.SING_BOX},
            "subscription_provider_mismatch",
        ),
    ],
)
async def test_disabled_resources_are_rejected(
    app_state: AppState, kwargs: dict, code: str
) -> None:
    ids = await _seed(app_state, **kwargs)
    service = await _service(app_state)

    with pytest.raises(ValidationError) as exc_info:
        await service.generate_config(ids["assignment_id"])

    assert exc_info.value.code == code


def test_renderer_validation_and_immutable_rendering() -> None:
    renderer = SubscriptionRenderer()
    config = ProviderConfig(
        assignment_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider_kind=ProviderKind.XRAY,
        provider_name="xray",
        protocol="wireguard",
        client_id="client",
        email=None,
        inbound_tag="profile",
        host="example.com",
        port=443,
        expires_at=None,
        traffic_limit_bytes=None,
        settings={},
    )

    with pytest.raises(ValidationError):
        renderer.render_config(config)
    with pytest.raises(FrozenInstanceError):
        config.protocol = "vless"  # type: ignore[misc]


async def test_provider_compatibility_requires_registered_provider(app_state: AppState) -> None:
    ids = await _seed(app_state)
    service = SubscriptionService(
        SubscriptionRepository(app_state.db.sessionmaker()),
        SubscriptionGenerator(ProviderRegistry()),
        SubscriptionRenderer(),
        app_state.cache,
    )

    with pytest.raises(ValidationError) as exc_info:
        await service.generate_config(ids["assignment_id"])

    assert exc_info.value.code == "subscription_provider_unavailable"


def test_no_direct_xray_imports_outside_provider_layer() -> None:
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    offenders = []
    for path in (root / "app").rglob("*.py"):
        if "/providers/" in path.as_posix():
            continue
        if "/tests/" in path.as_posix():
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [name.name for name in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                if module == "app.providers.xray" or module.startswith("app.providers.xray."):
                    offenders.append(f"{path.relative_to(root)}: {module}")
    assert offenders == []
