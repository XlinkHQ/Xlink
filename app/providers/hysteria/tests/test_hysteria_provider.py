from __future__ import annotations

import pytest

from app.providers.base.exceptions import ClientNotFoundError
from app.providers.base.models import ClientSpec
from app.providers.hysteria.provider import HysteriaProvider


@pytest.mark.asyncio
async def test_create_generates_strong_secret(tmp_path):
    provider = HysteriaProvider(data_dir=str(tmp_path))
    result = await provider.create_client(ClientSpec(client_id="c1"))
    assert len(result.raw["password"]) >= 24


@pytest.mark.asyncio
async def test_obfs_adds_second_secret(tmp_path):
    provider = HysteriaProvider(data_dir=str(tmp_path))
    result = await provider.create_client(
        ClientSpec(client_id="c2", attributes={"obfs": "salamander"})
    )
    assert result.raw["obfs_password"]
    assert result.raw["password"] != result.raw["obfs_password"]


@pytest.mark.asyncio
async def test_get_then_delete(tmp_path):
    provider = HysteriaProvider(data_dir=str(tmp_path))
    created = await provider.create_client(ClientSpec(client_id="c3"))
    fetched = await provider.get_client("c3")
    assert fetched.raw["password"] == created.raw["password"]
    await provider.delete_client("c3")
    with pytest.raises(ClientNotFoundError):
        await provider.get_client("c3")


@pytest.mark.asyncio
async def test_update_preserves_passwords(tmp_path):
    provider = HysteriaProvider(data_dir=str(tmp_path))
    created = await provider.create_client(
        ClientSpec(client_id="c4", attributes={"obfs": "salamander", "bandwidth": "100"})
    )
    updated = await provider.update_client(
        ClientSpec(client_id="c4", attributes={"bandwidth": "200"})
    )
    assert updated.raw["password"] == created.raw["password"]
    assert updated.raw["obfs_password"] == created.raw["obfs_password"]
    assert "bandwidth" not in updated.raw


@pytest.mark.asyncio
async def test_persistence_across_restart(tmp_path):
    provider1 = HysteriaProvider(data_dir=str(tmp_path))
    created = await provider1.create_client(
        ClientSpec(client_id="c5", attributes={"obfs": "salamander"})
    )

    provider2 = HysteriaProvider(data_dir=str(tmp_path))
    fetched = await provider2.get_client("c5")
    assert fetched.raw["password"] == created.raw["password"]
    assert fetched.raw["obfs_password"] == created.raw["obfs_password"]
