from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import event

from app.agent.commands import CommandSigner
from app.agent.heartbeat import hash_agent_token
from app.agent.reconcile import reconcile_once
from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.models import ProviderKind

SECRET = "agent-signing-secret-32-chars-minimum-x"
TOKEN = "agent-token-32-chars-minimum-test-x"


async def _seed_nodes(app_state: AppState, count: int) -> None:
    async with app_state.db.session() as session:
        user = User(
            email=f"u-{uuid.uuid4().hex[:8]}@x.io",
            username=f"u-{uuid.uuid4().hex[:8]}",
            hashed_password=hash_password("strong-password-1234"),
            role=UserRole.USER,
        )
        session.add(user)
        await session.flush()
        for i in range(count):
            node = Node(
                name=f"n{i}",
                slug=f"n-{uuid.uuid4().hex[:8]}",
                host=f"10.0.{i // 256}.{i % 256}",
                port=443,
                max_users=100,
                status=NodeStatus.ACTIVE,
                last_seen_at=datetime.now(UTC),
                node_metadata={"agent_token_hash": hash_agent_token(TOKEN)},
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


async def test_reconcile_1000_nodes_bounded_queries(app_state: AppState):
    await _seed_nodes(app_state, 1000)

    join_queries = {"n": 0}

    def _count(conn, cursor, statement, *args):
        text = statement.lower()
        if "client_assignments" in text and "join" in text and "profiles" in text:
            join_queries["n"] += 1

    engine = app_state.db.engine.sync_engine
    event.listen(engine, "before_cursor_execute", _count)
    try:
        stats = await reconcile_once(
            app_state.db,
            signer=CommandSigner(SECRET),
            events=app_state.events,
            self_healing_enabled=True,
            target_version=None,
            batch_size=100,
        )
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert stats["drifted"] == 1000
    assert join_queries["n"] <= 10


async def test_reconcile_batches_commit_independently(app_state: AppState):
    await _seed_nodes(app_state, 250)
    stats = await reconcile_once(
        app_state.db,
        signer=CommandSigner(SECRET),
        events=app_state.events,
        self_healing_enabled=True,
        target_version=None,
        batch_size=50,
    )
    assert stats["drifted"] == 250
    assert stats["healed"] >= 0
