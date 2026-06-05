from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import NotFoundError, ValidationError
from app.provider_sdk.manifest import ProviderManifest
from app.provider_sdk.service import ProviderSDKService
from app.providers.base.models import (
    ClientResult,
    ClientSpec,
    ProviderCapability,
    ProviderKind,
    ProviderMetadata,
)
from app.providers.base.provider import Provider
from app.providers.base.registry import ProviderRegistry


class DummyProvider(Provider):
    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name="dummy",
            kind=ProviderKind.WIREGUARD,
            version="1.0.0",
            capabilities=frozenset({ProviderCapability.CREATE_CLIENT}),
        )

    async def create_client(self, spec: ClientSpec) -> ClientResult:
        return ClientResult(client_id=spec.client_id, provider=self.name)

    async def update_client(self, spec: ClientSpec) -> ClientResult:
        self.ensure_capability(ProviderCapability.UPDATE_CLIENT)
        return ClientResult(client_id=spec.client_id, provider=self.name)

    async def delete_client(self, client_id: str) -> None:
        self.ensure_capability(ProviderCapability.DELETE_CLIENT)

    async def get_client(self, client_id: str) -> ClientResult:
        self.ensure_capability(ProviderCapability.GET_CLIENT)
        return ClientResult(client_id=client_id, provider=self.name)


def _manifest(**overrides) -> ProviderManifest:
    data = {
        "name": "dummy",
        "kind": "wireguard",
        "version": "1.0.0",
        "min_platform_version": "0.1.0",
        "capabilities": ["create_client"],
    }
    data.update(overrides)
    return ProviderManifest.model_validate(data)


def test_manifest_validation() -> None:
    manifest = _manifest()

    assert manifest.kind is ProviderKind.WIREGUARD
    assert ProviderCapability.CREATE_CLIENT in manifest.capabilities


def test_invalid_manifest_rejected() -> None:
    with pytest.raises(PydanticValidationError):
        _manifest(name="../bad")


def test_register_from_manifest() -> None:
    registry = ProviderRegistry()
    service = ProviderSDKService(
        registry=registry,
        providers={"dummy": DummyProvider()},
    )

    provider = service.register_from_manifest(_manifest())

    assert provider.name == "dummy"
    assert registry.get("dummy") is provider


def test_capability_mismatch_rejected() -> None:
    service = ProviderSDKService(
        registry=ProviderRegistry(),
        providers={"dummy": DummyProvider()},
    )
    manifest = _manifest(capabilities=["create_client", "delete_client"])

    with pytest.raises(ValidationError) as exc_info:
        service.register_from_manifest(manifest)

    assert exc_info.value.code == "provider_capability_mismatch"


def test_platform_version_rejected() -> None:
    service = ProviderSDKService(
        registry=ProviderRegistry(),
        providers={"dummy": DummyProvider()},
        platform_version="0.1.0",
    )

    with pytest.raises(ValidationError) as exc_info:
        service.register_from_manifest(_manifest(min_platform_version="9.0.0"))

    assert exc_info.value.code == "provider_platform_version_unsupported"


def test_missing_provider_rejected() -> None:
    service = ProviderSDKService(registry=ProviderRegistry(), providers={})

    with pytest.raises(NotFoundError) as exc_info:
        service.register_from_manifest(_manifest())

    assert exc_info.value.code == "provider_implementation_not_found"


def test_capability_negotiation() -> None:
    service = ProviderSDKService(
        registry=ProviderRegistry(),
        providers={"dummy": DummyProvider()},
    )

    negotiated = service.negotiate(_manifest(), DummyProvider())

    assert negotiated == frozenset({"create_client"})
