from __future__ import annotations

import json
import uuid
from types import MappingProxyType

from app.providers.base.models import ProviderKind
from app.subscription.formats import singbox, wireguard, xray_json
from app.subscription.formats import vless as vless_fmt
from app.subscription.models import ProviderConfig


def _config(protocol: str, settings: dict) -> ProviderConfig:
    return ProviderConfig(
        assignment_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider_kind=ProviderKind.XRAY,
        provider_name="p",
        protocol=protocol,
        client_id=str(uuid.uuid4()),
        email="e@x",
        inbound_tag="in",
        host="example.com",
        port=443,
        expires_at=None,
        traffic_limit_bytes=None,
        settings=MappingProxyType(settings),
    )


def test_singbox_alpn_list_not_stringified() -> None:
    cfg = _config(
        "vless",
        {
            "uuid": str(uuid.uuid4()),
            "security": "tls",
            "alpn": ["h2", "http/1.1"],
            "network": "tcp",
        },
    )
    out = json.loads(singbox.render((cfg,)))
    tls = out["outbounds"][0]["tls"]
    assert tls["alpn"] == ["h2", "http/1.1"]


def test_singbox_hysteria2_always_has_tls() -> None:
    cfg = _config("hysteria2", {"password": "pw", "security": "none"})
    out = json.loads(singbox.render((cfg,)))
    ob = out["outbounds"][0]
    assert ob["tls"]["enabled"] is True
    assert ob["tls"]["server_name"] == "example.com"


def test_singbox_tuic_always_has_tls() -> None:
    cfg = _config("tuic", {"uuid": str(uuid.uuid4()), "password": "pw"})
    out = json.loads(singbox.render((cfg,)))
    assert out["outbounds"][0]["tls"]["enabled"] is True


def test_xray_json_alpn_list_not_stringified() -> None:
    cfg = _config(
        "vless",
        {
            "uuid": str(uuid.uuid4()),
            "security": "tls",
            "alpn": ["h2", "http/1.1"],
            "network": "tcp",
        },
    )
    out = json.loads(xray_json.render((cfg,)))
    tls = out[0]["outbounds"][0]["streamSettings"]["tlsSettings"]
    assert tls["alpn"] == ["h2", "http/1.1"]


def test_vless_uri_alpn_list_joined() -> None:
    cfg = _config(
        "vless",
        {
            "uuid": str(uuid.uuid4()),
            "security": "tls",
            "alpn": ["h2", "http/1.1"],
            "network": "tcp",
        },
    )
    uri = vless_fmt.render(cfg)
    assert "alpn=h2%2Chttp%2F1.1" in uri or "alpn=h2,http/1.1" in uri
    assert "%5B%27" not in uri and "['" not in uri


def _wg_config(host: str, settings: dict) -> ProviderConfig:
    base = {"privateKey": "cGFk" * 11, "publicKey": "cGFk" * 11, **settings}
    return ProviderConfig(
        assignment_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider_kind=ProviderKind.WIREGUARD,
        provider_name="p",
        protocol="wireguard",
        client_id=str(uuid.uuid4()),
        email="e@x",
        inbound_tag="wg",
        host=host,
        port=6721,
        expires_at=None,
        traffic_limit_bytes=None,
        settings=MappingProxyType(base),
    )


def test_wireguard_full_tunnel_appends_ipv6():
    cfg = _wg_config("1.2.3.4", {"address": "10.8.0.2/32", "allowedIPs": "0.0.0.0/0"})
    out = wireguard.render_one(cfg)
    assert "::/0" in out


def test_wireguard_ipv6_endpoint_is_bracketed():
    cfg = _wg_config("2001:db8::1", {"address": "10.8.0.2/32"})
    out = wireguard.render_one(cfg)
    assert "Endpoint = [2001:db8::1]:6721" in out
