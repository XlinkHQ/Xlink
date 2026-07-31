from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.providers.base.registry import ProviderRegistry
from app.subscription.generator import SubscriptionGenerator


def _source(credentials: dict) -> SimpleNamespace:
    user = SimpleNamespace(
        email="u@x", username="u", data_limit_bytes=None, expire_at=None
    )
    assignment = SimpleNamespace(
        id=uuid.uuid4(), user=user, traffic_limit_bytes=None, credentials=credentials
    )
    profile = SimpleNamespace(
        name="wg",
        slug="wg",
        protocol="wireguard",
        settings={"address": "10.8.0.1/24", "presharedKey": "x"},
    )
    node = SimpleNamespace(host="1.2.3.4", slug="n")
    return SimpleNamespace(assignment=assignment, profile=profile, node=node)


def test_client_never_inherits_server_address() -> None:
    gen = SubscriptionGenerator(ProviderRegistry())
    base = gen._base_settings(_source({"preshared_key": "x"}), 0, None)
    assert base.get("address") != "10.8.0.1/24"


def test_client_uses_its_own_credential_address() -> None:
    gen = SubscriptionGenerator(ProviderRegistry())
    base = gen._base_settings(
        _source({"address": "10.8.0.7/32", "preshared_key": "x"}), 0, None
    )
    assert base["address"] == "10.8.0.7/32"
