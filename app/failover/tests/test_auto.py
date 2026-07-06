from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from app.events.models import NodeOffline, NodeRecovered
from app.failover.auto import AutoFailoverHandler


@dataclass
class _Result:
    migrated: int = 2
    skipped: int = 0


class _FakeService:
    def __init__(self, *, raises: bool = False) -> None:
        self.calls: list[uuid.UUID] = []
        self._raises = raises

    async def failover_node(self, node_id: uuid.UUID, **_: object) -> _Result:
        self.calls.append(node_id)
        if self._raises:
            raise RuntimeError("boom")
        return _Result()


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.asyncio
async def test_fires_failover_on_node_offline() -> None:
    svc = _FakeService()
    handler = AutoFailoverHandler(svc, cooldown_seconds=300, clock=_Clock())
    node_id = uuid.uuid4()

    await handler(NodeOffline(node_id=node_id, reason="heartbeat_stale"))

    assert svc.calls == [node_id]


@pytest.mark.asyncio
async def test_ignores_unrelated_events() -> None:
    svc = _FakeService()
    handler = AutoFailoverHandler(svc, cooldown_seconds=300, clock=_Clock())

    await handler(NodeRecovered(node_id=uuid.uuid4()))

    assert svc.calls == []


@pytest.mark.asyncio
async def test_cooldown_skips_repeat_within_window() -> None:
    svc = _FakeService()
    clock = _Clock()
    handler = AutoFailoverHandler(svc, cooldown_seconds=300, clock=clock)
    node_id = uuid.uuid4()

    await handler(NodeOffline(node_id=node_id))
    clock.now = 299
    await handler(NodeOffline(node_id=node_id))

    assert svc.calls == [node_id]


@pytest.mark.asyncio
async def test_cooldown_expires_allows_retry() -> None:
    svc = _FakeService()
    clock = _Clock()
    handler = AutoFailoverHandler(svc, cooldown_seconds=300, clock=clock)
    node_id = uuid.uuid4()

    await handler(NodeOffline(node_id=node_id))
    clock.now = 301
    await handler(NodeOffline(node_id=node_id))

    assert svc.calls == [node_id, node_id]


@pytest.mark.asyncio
async def test_cooldown_is_per_node() -> None:
    svc = _FakeService()
    handler = AutoFailoverHandler(svc, cooldown_seconds=300, clock=_Clock())
    a, b = uuid.uuid4(), uuid.uuid4()

    await handler(NodeOffline(node_id=a))
    await handler(NodeOffline(node_id=b))

    assert svc.calls == [a, b]


@pytest.mark.asyncio
async def test_swallows_service_errors() -> None:
    svc = _FakeService(raises=True)
    handler = AutoFailoverHandler(svc, cooldown_seconds=300, clock=_Clock())

    await handler(NodeOffline(node_id=uuid.uuid4()))

    assert len(svc.calls) == 1
