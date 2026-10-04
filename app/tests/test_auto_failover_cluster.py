"""Auto-failover cooldown is cluster-wide: two handlers (two replicas, or one
replica before and after a leader handover) must not fail the same node over
twice within the cooldown."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import fakeredis

from app.events.models import NodeOffline
from app.failover.auto import AutoFailoverHandler


class _Service:
    def __init__(self) -> None:
        self.calls = 0

    async def failover_node(self, _node_id):  # noqa: ANN001, ANN202
        self.calls += 1
        return SimpleNamespace(migrated=0, skipped=0)


async def test_cooldown_is_shared_across_handlers() -> None:
    cache = SimpleNamespace(client=fakeredis.aioredis.FakeRedis())
    service = _Service()
    a = AutoFailoverHandler(service, cooldown_seconds=300, cache=cache)
    b = AutoFailoverHandler(service, cooldown_seconds=300, cache=cache)
    node = uuid.uuid4()
    await a(NodeOffline(node_id=node, reason="heartbeat_stale"))
    await b(NodeOffline(node_id=node, reason="heartbeat_stale"))
    assert service.calls == 1
    await b(NodeOffline(node_id=uuid.uuid4(), reason="heartbeat_stale"))
    assert service.calls == 2


async def test_redis_failure_falls_back_to_local_cooldown() -> None:
    class _Down:
        @property
        def client(self):  # noqa: ANN202
            raise ConnectionError("down")

    service = _Service()
    h = AutoFailoverHandler(service, cooldown_seconds=300, cache=_Down())
    node = uuid.uuid4()
    await h(NodeOffline(node_id=node, reason="x"))
    await h(NodeOffline(node_id=node, reason="x"))
    assert service.calls == 1
