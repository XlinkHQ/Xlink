from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.notifications.job import NotificationJob
from app.providers.base.models import ProviderKind
from app.webhooks import events
from app.webhooks.dispatcher import WebhookDispatcher


class _CapturingDispatcher:
    enabled = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    async def dispatch(self, action: str, username: str, detail: str | None = None) -> None:
        self.calls.append((action, username, detail))


async def _seed_user(
    app_state: AppState,
    *,
    expire_at: datetime | None = None,
    data_limit: int | None = None,
    used: int = 0,
) -> uuid.UUID:
    async with app_state.db.session() as session:
        user = User(
            email=f"u-{uuid.uuid4().hex[:8]}@x.io",
            username=f"u-{uuid.uuid4().hex[:8]}",
            hashed_password=hash_password("strong-password-1234-AB!"),
            role=UserRole.USER,
            expire_at=expire_at,
            data_limit_bytes=data_limit,
        )
        session.add(user)
        await session.flush()
        uid = user.id
        if used:
            node = Node(
                name="n",
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
            session.add(
                ClientAssignment(
                    user_id=uid,
                    profile_id=profile.id,
                    node_id=node.id,
                    provider_kind=ProviderKind.XRAY,
                    status=AssignmentStatus.ACTIVE,
                    used_bytes=used,
                )
            )
            await session.flush()
    return uid


def _job(app_state: AppState, dispatcher) -> NotificationJob:
    return NotificationJob(
        app_state.db,
        dispatcher,
        app_state.cache,
        interval_seconds=3600,
        expiring_days=3,
        usage_percent=80,
    )


async def test_expiring_soon_dispatched(app_state: AppState):
    await _seed_user(app_state, expire_at=datetime.now(UTC) + timedelta(days=2))
    disp = _CapturingDispatcher()
    sent = await _job(app_state, disp).scan_once()
    assert sent == 1
    assert disp.calls[0][0] == events.USER_EXPIRING_SOON


async def test_not_expiring_yet(app_state: AppState):
    await _seed_user(app_state, expire_at=datetime.now(UTC) + timedelta(days=30))
    disp = _CapturingDispatcher()
    assert await _job(app_state, disp).scan_once() == 0


async def test_data_warning_dispatched(app_state: AppState):
    await _seed_user(app_state, data_limit=1000, used=900)
    disp = _CapturingDispatcher()
    sent = await _job(app_state, disp).scan_once()
    assert sent == 1
    assert disp.calls[0][0] == events.USER_DATA_WARNING
    assert "90%" in (disp.calls[0][2] or "")


async def test_data_under_threshold(app_state: AppState):
    await _seed_user(app_state, data_limit=1000, used=500)
    disp = _CapturingDispatcher()
    assert await _job(app_state, disp).scan_once() == 0


async def test_dedup_prevents_repeat(app_state: AppState):
    await _seed_user(app_state, expire_at=datetime.now(UTC) + timedelta(days=1))
    disp = _CapturingDispatcher()
    job = _job(app_state, disp)
    assert await job.scan_once() == 1

    assert await job.scan_once() == 0


def test_telegram_enabled_flag():
    off = WebhookDispatcher(Settings(database_url_override="sqlite+aiosqlite:///:memory:"))
    assert off.telegram_enabled is False
    on = WebhookDispatcher(
        Settings(
            database_url_override="sqlite+aiosqlite:///:memory:",
            telegram_bot_token="123:abc",
            telegram_chat_ids="111, 222",
        )
    )
    assert on.telegram_enabled is True
    assert on.enabled is True


def test_dispatcher_text_includes_detail():
    disp = WebhookDispatcher(Settings(database_url_override="sqlite+aiosqlite:///:memory:"))
    text = disp._text(
        {"action": events.USER_EXPIRING_SOON, "username": "alice", "detail": "Expires in 2 day(s)"}
    )
    assert "alice" in text
    assert "Expires in 2 day(s)" in text
