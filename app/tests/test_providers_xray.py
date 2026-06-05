from __future__ import annotations

import pytest

from app.providers.base.exceptions import (
    ClientAlreadyExistsError,
    ClientNotFoundError,
)
from app.providers.base.models import ClientSpec, ProviderCapability, ProviderKind
from app.providers.discovery import build_registry
from app.providers.xray.provider import XrayProvider


def _spec(client_id: str = "c1", **attrs) -> ClientSpec:
    return ClientSpec(client_id=client_id, email="u@example.com", attributes=attrs)


def test_xray_metadata_capabilities() -> None:
    meta = XrayProvider().metadata
    assert meta.kind is ProviderKind.XRAY
    assert meta.name == "xray"
    assert meta.capabilities == frozenset(ProviderCapability)


async def test_create_get_client() -> None:
    p = XrayProvider()
    created = await p.create_client(_spec(flow="xtls-rprx-vision", level=1))
    assert created.client_id == "c1"
    assert created.provider == "xray"
    assert created.raw["flow"] == "xtls-rprx-vision"

    fetched = await p.get_client("c1")
    assert fetched.client_id == "c1"
    assert fetched.raw["level"] == 1


async def test_create_duplicate_raises() -> None:
    p = XrayProvider()
    await p.create_client(_spec())
    with pytest.raises(ClientAlreadyExistsError):
        await p.create_client(_spec())


async def test_update_client() -> None:
    p = XrayProvider()
    await p.create_client(_spec(level=0))
    updated = await p.update_client(_spec(level=5))
    assert updated.raw["level"] == 5


async def test_update_missing_raises() -> None:
    p = XrayProvider()
    with pytest.raises(ClientNotFoundError):
        await p.update_client(_spec())


async def test_delete_client() -> None:
    p = XrayProvider()
    await p.create_client(_spec())
    await p.delete_client("c1")
    with pytest.raises(ClientNotFoundError):
        await p.get_client("c1")


async def test_delete_missing_raises() -> None:
    p = XrayProvider()
    with pytest.raises(ClientNotFoundError):
        await p.delete_client("ghost")


async def test_get_missing_raises() -> None:
    p = XrayProvider()
    with pytest.raises(ClientNotFoundError):
        await p.get_client("ghost")


def test_discovery_registers_xray() -> None:
    reg = build_registry()
    assert "xray" in reg
    provider = reg.get_by_kind(ProviderKind.XRAY)
    assert isinstance(provider, XrayProvider)
