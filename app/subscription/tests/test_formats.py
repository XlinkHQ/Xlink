from __future__ import annotations

import base64
import json
import uuid

import pytest
import yaml

from app.providers.base.models import ProviderKind
from app.subscription.formats.base import FormatRenderError
from app.subscription.formats.registry import default_registry
from app.subscription.formats.uri import render_uri
from app.subscription.models import ProviderConfig
from app.subscription.renderer import SubscriptionRenderer
from app.subscription.schemas import SubscriptionFormat

CLIENT = "11111111-1111-1111-1111-111111111111"


def _cfg(protocol="vless", *, host="1.2.3.4", port=443, **settings) -> ProviderConfig:
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


SS = {"method": "aes-256-gcm", "password": "pw"}
TUIC = {"password": "pw"}
SOCKS = {"username": "u", "password": "p"}
NAIVE = {"username": "u", "password": "p"}
WG = {"peerPublicKey": "PUB", "privateKey": "PRIV"}


@pytest.mark.parametrize(
    "protocol,scheme,extra",
    [
        ("vless", "vless://", {}),
        ("vmess", "vmess://", {}),
        ("trojan", "trojan://", {}),
        ("shadowsocks", "ss://", SS),
        ("hysteria2", "hysteria2://", {}),
        ("tuic", "tuic://", TUIC),
        ("socks", "socks://", SOCKS),
        ("http", "http://", {}),
        ("naive", "naive+https://", NAIVE),
    ],
)
def test_uri_renderer_valid_and_deterministic(protocol, scheme, extra):
    config = _cfg(protocol, **extra)
    uri1 = render_uri(config)
    uri2 = render_uri(config)
    assert uri1.startswith(scheme)
    assert uri1 == uri2


def test_unsupported_protocol_uri():
    with pytest.raises(FormatRenderError):
        render_uri(_cfg("mtproto"))


def test_shadowsocks_defaults_to_credential():

    uri = render_uri(_cfg("shadowsocks"))
    assert uri.startswith("ss://")


def test_tuic_falls_back_to_credential():
    uri = render_uri(_cfg("tuic"))
    assert uri.startswith("tuic://")


def test_naive_missing_credentials():
    with pytest.raises(FormatRenderError):
        render_uri(_cfg("naive"))


def test_invalid_node_host_rejected():
    with pytest.raises(FormatRenderError):
        render_uri(_cfg("vless", host=""))


def test_invalid_node_port_rejected():
    with pytest.raises(FormatRenderError):
        render_uri(_cfg("vless", port=0))


def test_singbox_json_serialization():
    content = default_registry().render(
        SubscriptionFormat.SINGBOX_JSON, (_cfg("vless", security="tls", sni="x.io"),)
    )
    doc = json.loads(content)
    assert isinstance(doc["outbounds"], list)
    assert doc["outbounds"][0]["type"] == "vless"
    assert doc["outbounds"][0]["tls"]["enabled"] is True


def test_clash_yaml_serialization():
    content = default_registry().render(SubscriptionFormat.CLASH_YAML, (_cfg("trojan"),))
    doc = yaml.safe_load(content)
    assert doc["proxies"][0]["type"] == "trojan"
    assert doc["proxy-groups"][0]["name"] == "PROXY"


def test_mihomo_supports_hysteria2():
    content = default_registry().render(SubscriptionFormat.MIHOMO_YAML, (_cfg("hysteria2"),))
    doc = yaml.safe_load(content)
    assert doc["proxies"][0]["type"] == "hysteria2"


def test_clash_rejects_hysteria2():
    with pytest.raises(FormatRenderError):
        default_registry().render(SubscriptionFormat.CLASH_YAML, (_cfg("hysteria2"),))


def test_wireguard_conf_serialization():
    content = default_registry().render(
        SubscriptionFormat.WIREGUARD_CONF, (_cfg("wireguard", **WG),)
    )
    assert "[Interface]" in content
    assert "[Peer]" in content
    assert "PublicKey = PUB" in content


def test_wireguard_missing_peer_key_is_skipped_not_fatal():
    # A single config with bad stored data must be skipped, not 422 the whole
    # feed — a good config alongside it still renders, and an all-bad feed
    # yields empty rather than blowing up the public endpoint.
    mixed = default_registry().render(
        SubscriptionFormat.WIREGUARD_CONF,
        (_cfg("wireguard", **WG), _cfg("wireguard")),
    )
    assert "[Interface]" in mixed and "PublicKey = PUB" in mixed

    all_bad = default_registry().render(
        SubscriptionFormat.WIREGUARD_CONF, (_cfg("wireguard"),)
    )
    assert all_bad == ""


@pytest.mark.parametrize(
    "fmt,config",
    [
        (SubscriptionFormat.SINGBOX_JSON, _cfg("vless", security="tls", sni="x.io")),
        (SubscriptionFormat.CLASH_YAML, _cfg("vmess")),
        (SubscriptionFormat.MIHOMO_YAML, _cfg("tuic", **TUIC)),
        (SubscriptionFormat.WIREGUARD_CONF, _cfg("wireguard", **WG)),
        (SubscriptionFormat.TEXT, _cfg("vless")),
        (SubscriptionFormat.BASE64, _cfg("trojan")),
    ],
)
def test_container_format_deterministic(fmt, config):
    registry = default_registry()
    out1 = registry.render(fmt, (config,))
    out2 = registry.render(fmt, (config,))
    assert out1 == out2


def test_registry_has_all_formats():
    registry = default_registry()
    assert registry.formats() == set(SubscriptionFormat)


def test_registry_pluggable():
    registry = default_registry()
    sentinel = "CUSTOM"
    registry.register(SubscriptionFormat.TEXT, lambda configs: sentinel)
    assert registry.render(SubscriptionFormat.TEXT, (_cfg("vless"),)) == sentinel


def test_single_protocol_feed_filters():
    registry = default_registry()
    configs = (_cfg("vless"), _cfg("trojan"))
    content = registry.render(SubscriptionFormat.VLESS_URI, configs)
    assert content.count("vless://") == 1
    assert "trojan://" not in content


def test_single_protocol_feed_incompatible():
    registry = default_registry()
    with pytest.raises(FormatRenderError):
        registry.render(SubscriptionFormat.TUIC_URI, (_cfg("vless"),))


def test_text_format_regression():
    renderer = SubscriptionRenderer()
    config = _cfg("vless", network="ws", path="/p", security="tls", sni="x.io")
    feed = renderer.render_feed((config,), feed_format=SubscriptionFormat.TEXT)
    assert feed.content == render_uri(config)
    assert feed.content.startswith("vless://")


def test_base64_format_regression():
    renderer = SubscriptionRenderer()
    config = _cfg("vmess")
    feed = renderer.render_feed((config,), feed_format=SubscriptionFormat.BASE64)
    decoded = base64.b64decode(feed.content).decode("utf-8")
    assert decoded == render_uri(config)


def test_feed_content_hash_etag_stable():
    renderer = SubscriptionRenderer()
    config = _cfg("vless")
    a = renderer.render_feed((config,), feed_format=SubscriptionFormat.TEXT)
    b = renderer.render_feed((config,), feed_format=SubscriptionFormat.TEXT)
    assert a.content_hash == b.content_hash
    assert a.etag == f'"{a.content_hash}"'


def test_bad_int_setting_skips_config_not_feed():
    """A stored non-numeric numeric-setting (e.g. alterId='x') must skip just
    that config, never 500 the whole feed (public endpoint DoS guard)."""
    import uuid
    from types import MappingProxyType

    from app.subscription.models import ProviderConfig
    from app.subscription.renderer import SubscriptionRenderer
    from app.subscription.schemas import RenderVersion, SubscriptionFormat

    def mk(alter):
        return ProviderConfig(
            assignment_id=uuid.uuid4(), user_id=uuid.uuid4(), provider_kind=None,
            provider_name="p", protocol="vmess", client_id=str(uuid.uuid4()),
            email=None, inbound_tag="t", host="1.2.3.4", port=443, expires_at=None,
            traffic_limit_bytes=None,
            settings=MappingProxyType({"alterId": alter, "network": "tcp",
                                       "security": "none", "uuid": str(uuid.uuid4())}),
        )

    r = SubscriptionRenderer()
    good, bad = mk(0), mk("x")
    for fmt in (SubscriptionFormat.CLASH_YAML, SubscriptionFormat.SINGBOX_JSON,
                SubscriptionFormat.XRAY_JSON):
        out = r.render_feed((good, bad), version=RenderVersion.V1, feed_format=fmt)
        assert out.content  # good kept, bad skipped, no exception
