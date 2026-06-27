from __future__ import annotations

import json
import uuid

import pytest
import yaml

from app.providers.base.models import ProviderKind
from app.subscription.formats.base import FormatRenderError
from app.subscription.formats.registry import default_registry
from app.subscription.models import ProviderConfig
from app.subscription.schemas import SubscriptionFormat

CLIENT = "22222222-2222-2222-2222-222222222222"


def _cfg(protocol: str, *, host="1.2.3.4", port=443, **settings) -> ProviderConfig:
    return ProviderConfig(
        assignment_id=uuid.UUID(CLIENT),
        user_id=uuid.uuid4(),
        provider_kind=ProviderKind.XRAY,
        provider_name="xray",
        protocol=protocol,
        client_id=CLIENT,
        email="u@x.io",
        inbound_tag="in",
        host=host,
        port=port,
        expires_at=None,
        traffic_limit_bytes=None,
        settings=settings,
    )


def test_ss2022_singbox_uses_2022_cipher_by_default() -> None:
    reg = default_registry()
    out = reg.render(SubscriptionFormat.SINGBOX_JSON, (_cfg("shadowsocks2022", password="pw"),))
    doc = json.loads(out)
    ob = doc["outbounds"][0]
    assert ob["type"] == "shadowsocks"
    assert ob["method"] == "2022-blake3-aes-256-gcm"
    assert ob["password"] == "pw"


def test_ss2022_renders_in_ss_uri_feed() -> None:
    reg = default_registry()
    out = reg.render(SubscriptionFormat.SHADOWSOCKS_URI, (_cfg("shadowsocks2022", password="pw"),))
    assert out.startswith("ss://")


def test_ss2022_clash_meta_proxy() -> None:
    reg = default_registry()
    out = reg.render(SubscriptionFormat.MIHOMO_YAML, (_cfg("shadowsocks2022", password="pw"),))
    proxy = yaml.safe_load(out)["proxies"][0]
    assert proxy["type"] == "ss"
    assert proxy["cipher"] == "2022-blake3-aes-256-gcm"


def test_ss2022_honours_explicit_method() -> None:
    reg = default_registry()
    cfg = _cfg("shadowsocks2022", password="pw", method="2022-blake3-chacha20-poly1305")
    doc = json.loads(reg.render(SubscriptionFormat.SINGBOX_JSON, (cfg,)))
    assert doc["outbounds"][0]["method"] == "2022-blake3-chacha20-poly1305"


def test_shadowtls_singbox_emits_detour_pair() -> None:
    reg = default_registry()
    cfg = _cfg(
        "shadowtls",
        host="edge.example.com",
        password="ss-pw",
        shadowtls_password="st-pw",
        sni="www.microsoft.com",
    )
    doc = json.loads(reg.render(SubscriptionFormat.SINGBOX_JSON, (cfg,)))
    types = {o["type"] for o in doc["outbounds"]}
    assert types == {"shadowtls", "shadowsocks"}

    st = next(o for o in doc["outbounds"] if o["type"] == "shadowtls")
    inner = next(o for o in doc["outbounds"] if o["type"] == "shadowsocks")
    assert st["version"] == 3
    assert st["password"] == "st-pw"
    assert st["tls"]["server_name"] == "www.microsoft.com"

    assert inner["detour"] == st["tag"]
    assert inner["password"] == "ss-pw"
    assert "server" not in inner


def test_shadowtls_clash_meta_uses_plugin() -> None:
    reg = default_registry()
    cfg = _cfg("shadowtls", password="ss-pw", shadowtls_password="st-pw", sni="www.bing.com")
    proxy = yaml.safe_load(reg.render(SubscriptionFormat.MIHOMO_YAML, (cfg,)))["proxies"][0]
    assert proxy["type"] == "ss"
    assert proxy["plugin"] == "shadow-tls"
    assert proxy["plugin-opts"]["host"] == "www.bing.com"
    assert proxy["plugin-opts"]["password"] == "st-pw"
    assert proxy["plugin-opts"]["version"] == 3


def test_shadowtls_rejected_by_plain_clash() -> None:
    reg = default_registry()
    with pytest.raises(FormatRenderError):
        reg.render(SubscriptionFormat.CLASH_YAML, (_cfg("shadowtls", password="pw"),))
