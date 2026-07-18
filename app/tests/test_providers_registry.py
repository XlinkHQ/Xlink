from __future__ import annotations

import pytest

from app.providers.base.exceptions import (
    CapabilityNotSupportedError,
    ProviderAlreadyRegisteredError,
    ProviderNotFoundError,
)
from app.providers.base.models import (
    ClientResult,
    ClientSpec,
    ProviderCapability,
    ProviderKind,
    ProviderMetadata,
)
from app.providers.base.provider import Provider
from app.providers.base.registry import ProviderRegistry


class StubProvider(Provider):
    def __init__(self, name: str, kind: ProviderKind, caps: set[ProviderCapability]) -> None:
        self._name = name
        self._kind = kind
        self._caps = frozenset(caps)

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(name=self._name, kind=self._kind, capabilities=self._caps)

    async def create_client(self, spec: ClientSpec) -> ClientResult:
        self.ensure_capability(ProviderCapability.CREATE_CLIENT)
        return ClientResult(client_id=spec.client_id, provider=self._name)

    async def update_client(self, spec: ClientSpec) -> ClientResult:
        self.ensure_capability(ProviderCapability.UPDATE_CLIENT)
        return ClientResult(client_id=spec.client_id, provider=self._name)

    async def delete_client(self, client_id: str) -> None:
        self.ensure_capability(ProviderCapability.DELETE_CLIENT)

    async def get_client(self, client_id: str) -> ClientResult:
        self.ensure_capability(ProviderCapability.GET_CLIENT)
        return ClientResult(client_id=client_id, provider=self._name)


def _read_only() -> StubProvider:
    return StubProvider("readonly", ProviderKind.SING_BOX, {ProviderCapability.GET_CLIENT})


def test_register_and_get() -> None:
    reg = ProviderRegistry()
    p = _read_only()
    reg.register(p)
    assert reg.get("readonly") is p
    assert "readonly" in reg
    assert len(reg) == 1


def test_register_duplicate_raises() -> None:
    reg = ProviderRegistry()
    reg.register(_read_only())
    with pytest.raises(ProviderAlreadyRegisteredError):
        reg.register(_read_only())


def test_register_replace() -> None:
    reg = ProviderRegistry()
    reg.register(_read_only())
    replacement = _read_only()
    reg.register(replacement, replace=True)
    assert reg.get("readonly") is replacement


def test_get_unknown_raises() -> None:
    reg = ProviderRegistry()
    with pytest.raises(ProviderNotFoundError):
        reg.get("nope")


def test_get_by_kind() -> None:
    reg = ProviderRegistry()
    reg.register(_read_only())
    assert reg.get_by_kind(ProviderKind.SING_BOX).name == "readonly"
    with pytest.raises(ProviderNotFoundError):
        reg.get_by_kind(ProviderKind.WIREGUARD)


def test_discovery_and_names() -> None:
    reg = ProviderRegistry()
    reg.discover(
        [
            StubProvider("a", ProviderKind.HYSTERIA, {ProviderCapability.GET_CLIENT}),
            StubProvider("b", ProviderKind.WIREGUARD, {ProviderCapability.CREATE_CLIENT}),
        ]
    )
    assert reg.names() == ["a", "b"]
    assert len(reg.metadata()) == 2


async def test_capability_enforcement() -> None:
    p = _read_only()
    assert await p.get_client("x")
    with pytest.raises(CapabilityNotSupportedError):
        await p.create_client(ClientSpec(client_id="x"))


def test_metadata_supports() -> None:
    meta = ProviderMetadata(
        name="m",
        kind=ProviderKind.XRAY,
        capabilities=frozenset({ProviderCapability.GET_CLIENT}),
    )
    assert meta.supports(ProviderCapability.GET_CLIENT)
    assert not meta.supports(ProviderCapability.DELETE_CLIENT)
