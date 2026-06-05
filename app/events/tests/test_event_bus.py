from __future__ import annotations

import asyncio
import uuid
from dataclasses import FrozenInstanceError

import pytest

from app.events.bus import EventBus, EventBusConfig, RetryPolicy
from app.events.handlers import register_default_handlers
from app.events.models import (
    AssignmentCreated,
    AssignmentDisabled,
    DomainEvent,
    NodeOffline,
    SubscriptionGenerated,
)
from app.events.registry import EventRegistry
from app.providers.base.models import ProviderKind


def _assignment_created() -> AssignmentCreated:
    return AssignmentCreated(
        assignment_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        provider_kind=ProviderKind.XRAY,
        correlation_id="corr-1",
    )


async def test_publish_without_handlers_returns_empty_results() -> None:
    bus = EventBus()

    results = await bus.publish(_assignment_created())

    assert results == ()


async def test_subscribe_and_publish_typed_event() -> None:
    seen: list[DomainEvent] = []
    bus = EventBus(config=EventBusConfig(retry=RetryPolicy(max_attempts=1)))

    async def handler(event: DomainEvent) -> None:
        seen.append(event)

    bus.subscribe(AssignmentCreated, handler)
    results = await bus.publish(_assignment_created())

    assert seen and isinstance(seen[0], AssignmentCreated)
    assert len(results) == 1
    assert results[0].succeeded is True
    assert results[0].attempts == 1


async def test_handler_registration_replace_and_unsubscribe() -> None:
    calls: list[str] = []
    registry = EventRegistry()

    async def first(_: DomainEvent) -> None:
        calls.append("first")

    async def second(_: DomainEvent) -> None:
        calls.append("second")

    registry.subscribe(AssignmentCreated, first)
    registry.subscribe(AssignmentCreated, second, replace=True)
    assert registry.count(AssignmentCreated) == 1

    bus = EventBus(registry)
    await bus.publish(_assignment_created())
    registry.unsubscribe(AssignmentCreated, second)
    await bus.publish(_assignment_created())

    assert calls == ["second"]
    assert registry.count(AssignmentCreated) == 0


async def test_retry_support_until_success() -> None:
    attempts = 0
    bus = EventBus(
        config=EventBusConfig(
            retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.0),
            concurrent_handlers=False,
        )
    )

    async def flaky(_: DomainEvent) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("not yet")

    bus.subscribe(AssignmentCreated, flaky)
    results = await bus.publish(_assignment_created())

    assert attempts == 3
    assert results[0].succeeded is True
    assert results[0].attempts == 3


async def test_failure_isolation_between_handlers() -> None:
    calls: list[str] = []
    bus = EventBus(
        config=EventBusConfig(
            retry=RetryPolicy(max_attempts=2, base_delay_seconds=0.0),
            concurrent_handlers=True,
        )
    )

    async def failing(_: DomainEvent) -> None:
        calls.append("failing")
        raise RuntimeError("boom")

    async def succeeding(_: DomainEvent) -> None:
        calls.append("succeeding")

    bus.subscribe(AssignmentCreated, failing)
    bus.subscribe(AssignmentCreated, succeeding)
    results = await bus.publish(_assignment_created())

    assert any(result.succeeded is False and result.attempts == 2 for result in results)
    assert any(result.succeeded is True for result in results)
    assert "succeeding" in calls


async def test_concurrent_handlers_run_together() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    order: list[str] = []
    bus = EventBus(
        config=EventBusConfig(
            retry=RetryPolicy(max_attempts=1),
            concurrent_handlers=True,
        )
    )

    async def slow(_: DomainEvent) -> None:
        order.append("slow-start")
        started.set()
        await release.wait()
        order.append("slow-end")

    async def fast(_: DomainEvent) -> None:
        await started.wait()
        order.append("fast")
        release.set()

    bus.subscribe(AssignmentCreated, slow)
    bus.subscribe(AssignmentCreated, fast)
    results = await bus.publish(_assignment_created())

    assert [result.succeeded for result in results] == [True, True]
    assert order == ["slow-start", "fast", "slow-end"]


async def test_base_event_handler_receives_subclasses() -> None:
    seen: list[str] = []
    bus = EventBus(config=EventBusConfig(retry=RetryPolicy(max_attempts=1)))

    async def handler(event: DomainEvent) -> None:
        seen.append(event.event_name)

    bus.subscribe(DomainEvent, handler)
    await bus.publish(NodeOffline(node_id=uuid.uuid4(), reason="heartbeat"))

    assert seen == ["NodeOffline"]


def test_events_are_typed_and_immutable() -> None:
    event = AssignmentDisabled(
        assignment_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider_kind=ProviderKind.XRAY,
    )

    assert event.event_name == "AssignmentDisabled"
    with pytest.raises(FrozenInstanceError):
        event.provider_kind = ProviderKind.SING_BOX  # type: ignore[misc]


def test_default_handlers_register_all_domain_events() -> None:
    registry = EventRegistry()

    register_default_handlers(registry)

    assert registry.count(AssignmentCreated) == 1
    assert registry.count(NodeOffline) == 1
    assert registry.count(SubscriptionGenerated) == 1
