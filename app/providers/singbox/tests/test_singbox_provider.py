from __future__ import annotations

import uuid

import pytest

from app.providers.base.exceptions import ClientNotFoundError
from app.providers.base.models import ClientSpec
from app.providers.singbox.provider import SingBoxProvider


@pytest.mark.asyncio
async def test_create_generates_valid_uuid(tmp_path):
    provider = SingBoxProvider(data_dir=str(tmp_path))
    result = await provider.create_client(ClientSpec(client_id="c1"))
    parsed = uuid.UUID(result.raw["uuid"])
    assert str(parsed) == result.raw["uuid"]


@pytest.mark.asyncio
async def test_trojan_protocol_gets_password(tmp_path):
    provider = SingBoxProvider(data_dir=str(tmp_path))
    result = await provider.create_client(
        ClientSpec(client_id="c2", attributes={"protocol": "trojan"})
    )
    assert len(result.raw["password"]) >= 24


@pytest.mark.asyncio
async def test_get_then_delete(tmp_path):
    provider = SingBoxProvider(data_dir=str(tmp_path))
    created = await provider.create_client(ClientSpec(client_id="c3"))
    fetched = await provider.get_client("c3")
    assert fetched.raw["uuid"] == created.raw["uuid"]
    await provider.delete_client("c3")
    with pytest.raises(ClientNotFoundError):
        await provider.get_client("c3")


@pytest.mark.asyncio
async def test_update_preserves_uuid_and_password(tmp_path):
    provider = SingBoxProvider(data_dir=str(tmp_path))
    created = await provider.create_client(
        ClientSpec(client_id="c4", attributes={"protocol": "trojan", "settings": {"port": "443"}})
    )
    updated = await provider.update_client(
        ClientSpec(client_id="c4", attributes={"protocol": "trojan", "settings": {"port": "8443"}})
    )
    assert updated.raw["uuid"] == created.raw["uuid"]
    assert updated.raw["password"] == created.raw["password"]
    assert updated.raw["port"] == "8443"


@pytest.mark.asyncio
async def test_persistence_across_restart(tmp_path):
    provider1 = SingBoxProvider(data_dir=str(tmp_path))
    created = await provider1.create_client(
        ClientSpec(client_id="c5", attributes={"protocol": "trojan"})
    )

    provider2 = SingBoxProvider(data_dir=str(tmp_path))
    fetched = await provider2.get_client("c5")
    assert fetched.raw["uuid"] == created.raw["uuid"]
    assert fetched.raw["password"] == created.raw["password"]
