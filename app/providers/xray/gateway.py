from __future__ import annotations

import asyncio
import time
from typing import Any

from app.providers.base.models import ClientResult, ClientSpec
from app.providers.xray.adapter import (
    build_create_client_payload,
    build_delete_client_payload,
    build_update_client_payload,
    parse_client_response,
)
from app.providers.xray.client import XrayTransport
from app.providers.xray.config import XrayGatewayConfig
from app.providers.xray.exceptions import (
    XrayCircuitOpenError,
    XrayConnectionError,
    XrayGatewayError,
    XrayRetryExhaustedError,
    XrayTimeoutError,
    XrayTransportError,
)

_RETRYABLE = (XrayTimeoutError, XrayConnectionError, TimeoutError, ConnectionError)


class _CircuitState:
    def __init__(self) -> None:
        self.failures = 0
        self.open = False
        self.opened_at: float | None = None


class XrayGateway:
    def __init__(self, transport: XrayTransport, config: XrayGatewayConfig | None = None) -> None:
        self._transport = transport
        self._config = config or XrayGatewayConfig()
        self._circuit = _CircuitState()

    @property
    def config(self) -> XrayGatewayConfig:
        return self._config

    async def create_client(self, spec: ClientSpec) -> ClientResult:
        payload = build_create_client_payload(spec)
        raw = await self._dispatch("create", payload)
        return parse_client_response(raw)

    async def update_client(self, spec: ClientSpec) -> ClientResult:
        payload = build_update_client_payload(spec)
        raw = await self._dispatch("update", payload)
        return parse_client_response(raw)

    async def delete_client(self, client_id: str) -> None:
        payload = build_delete_client_payload(client_id)
        await self._dispatch("delete", payload)

    async def get_client(self, client_id: str) -> ClientResult:
        payload = {"operation": "get", "client_id": client_id}
        raw = await self._dispatch("get", payload)
        return parse_client_response(raw)

    async def health_check(self) -> bool:
        try:
            return await asyncio.wait_for(
                self._transport.health(), timeout=self._config.timeout_seconds
            )
        except Exception:
            return False

    async def _dispatch(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._check_circuit()
        last_error: Exception | None = None
        for attempt in range(1, self._config.retry.max_attempts + 1):
            try:
                result = await self._call(operation, payload)
                self._record_success()
                return result
            except _RETRYABLE as exc:
                last_error = self._map_error(exc)
                self._record_failure()
                if attempt < self._config.retry.max_attempts:
                    await asyncio.sleep(self._config.retry.delay_for(attempt))
                    continue
            except XrayGatewayError:
                self._record_failure()
                raise
        raise XrayRetryExhaustedError(
            "Xray gateway exhausted retries.",
            details={"operation": operation, "attempts": self._config.retry.max_attempts},
        ) from last_error

    async def _call(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(
                self._transport.send(operation, payload),
                timeout=self._config.timeout_seconds,
            )
        except TimeoutError as exc:
            raise XrayTimeoutError(details={"operation": operation}) from exc
        except ConnectionError as exc:
            raise XrayConnectionError(details={"operation": operation}) from exc

    def _map_error(self, exc: Exception) -> Exception:
        if isinstance(exc, XrayGatewayError):
            return exc
        if isinstance(exc, TimeoutError):
            return XrayTimeoutError()
        if isinstance(exc, ConnectionError):
            return XrayConnectionError()
        return XrayTransportError(str(exc))

    def _check_circuit(self) -> None:
        cb = self._config.circuit_breaker
        if not (cb.enabled and self._circuit.open):
            return
        if (
            self._circuit.opened_at is not None
            and time.monotonic() - self._circuit.opened_at >= cb.reset_timeout_seconds
        ):
            # Half-open: allow one trial request. Reset the failure count below the
            # threshold so a single failure doesn't immediately re-open with a fresh
            # full cooldown; only repeated failures will trip the breaker again.
            self._circuit.open = False
            self._circuit.failures = max(0, cb.failure_threshold - 1)
            return
        raise XrayCircuitOpenError()

    def _record_failure(self) -> None:
        cb = self._config.circuit_breaker
        self._circuit.failures += 1
        if cb.enabled and self._circuit.failures >= cb.failure_threshold:
            self._circuit.open = True
            self._circuit.opened_at = time.monotonic()

    def _record_success(self) -> None:
        self._circuit.failures = 0
        self._circuit.open = False
        self._circuit.opened_at = None
