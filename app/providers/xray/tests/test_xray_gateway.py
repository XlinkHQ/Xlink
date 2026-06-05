from __future__ import annotations

import pytest

from app.providers.base.exceptions import ClientNotFoundError
from app.providers.base.models import ClientSpec
from app.providers.xray.client import InMemoryTransport, XrayTransport
from app.providers.xray.config import RetryPolicy, XrayGatewayConfig
from app.providers.xray.exceptions import (
    XrayConnectionError,
    XrayRetryExhaustedError,
    XrayTimeoutError,
)
from app.providers.xray.gateway import XrayGateway

VALID_UUID = "11111111-1111-1111-1111-111111111111"


def _spec(client_id=VALID_UUID, **attrs):
    attributes = {"protocol": "vless"}
    attributes.update(attrs)
    return ClientSpec(client_id=client_id, email="u@x.io", attributes=attributes)


class ScriptedTransport(XrayTransport):
    def __init__(self, behaviors):
        self._behaviors = list(behaviors)
        self.calls = 0
        self._inner = InMemoryTransport()

    async def health(self) -> bool:
        return True

    async def send(self, operation, payload):
        self.calls += 1
        if self._behaviors:
            behavior = self._behaviors.pop(0)
            if behavior is not None:
                raise behavior
        return await self._inner.send(operation, payload)


def _fast_config():
    return XrayGatewayConfig(
        timeout_seconds=0.5,
        retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.0, max_delay_seconds=0.0),
    )


async def test_create_client_success():
    gw = XrayGateway(InMemoryTransport(), _fast_config())
    result = await gw.create_client(_spec())
    assert result.client_id == VALID_UUID
    assert result.provider == "xray"


async def test_update_client_success():
    transport = InMemoryTransport()
    gw = XrayGateway(transport, _fast_config())
    await gw.create_client(_spec())
    result = await gw.update_client(_spec(level=3))
    assert result.raw["level"] == 3


async def test_delete_client_success():
    transport = InMemoryTransport()
    gw = XrayGateway(transport, _fast_config())
    await gw.create_client(_spec())
    await gw.delete_client(VALID_UUID)
    with pytest.raises(ClientNotFoundError):
        await gw.get_client(VALID_UUID)


async def test_get_client_success():
    transport = InMemoryTransport()
    gw = XrayGateway(transport, _fast_config())
    await gw.create_client(_spec(flow="vision"))
    result = await gw.get_client(VALID_UUID)
    assert result.raw["flow"] == "vision"


async def test_timeout_handling():
    transport = ScriptedTransport([TimeoutError(), TimeoutError(), TimeoutError()])
    gw = XrayGateway(transport, _fast_config())
    with pytest.raises(XrayRetryExhaustedError):
        await gw.create_client(_spec())
    assert transport.calls == 3


async def test_retry_handling_then_success():
    transport = ScriptedTransport([ConnectionError(), None])
    gw = XrayGateway(transport, _fast_config())
    result = await gw.create_client(_spec())
    assert result.client_id == VALID_UUID
    assert transport.calls == 2


async def test_connection_failure():
    transport = ScriptedTransport([ConnectionError(), ConnectionError(), ConnectionError()])
    gw = XrayGateway(transport, _fast_config())
    with pytest.raises(XrayRetryExhaustedError):
        await gw.create_client(_spec())


async def test_provider_error_mapping():
    transport = ScriptedTransport([TimeoutError()])
    gw = XrayGateway(
        transport, XrayGatewayConfig(timeout_seconds=0.5, retry=RetryPolicy(max_attempts=1))
    )
    with pytest.raises(XrayRetryExhaustedError) as exc_info:
        await gw.create_client(_spec())
    assert isinstance(exc_info.value.__cause__, (XrayTimeoutError, XrayConnectionError))


async def test_health_check():
    transport = InMemoryTransport()
    gw = XrayGateway(transport, _fast_config())
    assert await gw.health_check() is True
    transport.set_healthy(False)
    assert await gw.health_check() is False
