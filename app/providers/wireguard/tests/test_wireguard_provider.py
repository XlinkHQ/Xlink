from __future__ import annotations

import base64

import pytest

from app.providers.base.exceptions import ClientNotFoundError
from app.providers.base.models import ClientSpec
from app.providers.wireguard.provider import WireGuardProvider


@pytest.mark.asyncio
async def test_create_returns_real_keypair(tmp_path):
    provider = WireGuardProvider(data_dir=str(tmp_path))
    result = await provider.create_client(
        ClientSpec(client_id="c1", attributes={"address": "10.0.0.5/32"})
    )
    private_key = result.raw["private_key"]
    public_key = result.raw["public_key"]
    assert private_key and public_key
    assert private_key != public_key
    assert len(base64.standard_b64decode(private_key)) == 32
    assert len(base64.standard_b64decode(public_key)) == 32
    assert result.raw["address"] == "10.0.0.5/32"


@pytest.mark.asyncio
async def test_get_returns_stored_client(tmp_path):
    provider = WireGuardProvider(data_dir=str(tmp_path))
    created = await provider.create_client(ClientSpec(client_id="c2"))
    fetched = await provider.get_client("c2")
    assert fetched.raw["private_key"] == created.raw["private_key"]


@pytest.mark.asyncio
async def test_delete_removes_client(tmp_path):
    provider = WireGuardProvider(data_dir=str(tmp_path))
    await provider.create_client(ClientSpec(client_id="c3"))
    await provider.delete_client("c3")
    with pytest.raises(ClientNotFoundError):
        await provider.get_client("c3")


@pytest.mark.asyncio
async def test_update_preserves_keypair(tmp_path):
    provider = WireGuardProvider(data_dir=str(tmp_path))
    created = await provider.create_client(
        ClientSpec(client_id="c4", attributes={"address": "10.0.0.1/32", "dns": "1.1.1.1"})
    )
    updated = await provider.update_client(
        ClientSpec(client_id="c4", attributes={"address": "10.0.0.2/32"})
    )
    assert updated.raw["private_key"] == created.raw["private_key"]
    assert updated.raw["public_key"] == created.raw["public_key"]
    assert updated.raw["address"] == "10.0.0.2/32"


@pytest.mark.asyncio
async def test_persistence_across_restart(tmp_path):
    provider1 = WireGuardProvider(data_dir=str(tmp_path))
    created = await provider1.create_client(
        ClientSpec(client_id="c5", attributes={"address": "10.0.0.5/32"})
    )

    provider2 = WireGuardProvider(data_dir=str(tmp_path))
    fetched = await provider2.get_client("c5")
    assert fetched.raw["private_key"] == created.raw["private_key"]
    assert fetched.raw["public_key"] == created.raw["public_key"]
    assert fetched.raw["address"] == "10.0.0.5/32"
