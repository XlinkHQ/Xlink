from __future__ import annotations

import base64
import json
import uuid
from urllib.parse import parse_qs, urlparse

from app.providers.base.models import ProviderKind
from app.subscription.models import ProviderConfig
from app.subscription.renderer import SubscriptionRenderer

CLIENT = "11111111-1111-1111-1111-111111111111"


def _cfg(protocol="vless", **settings) -> ProviderConfig:
    return ProviderConfig(
        assignment_id=uuid.UUID(CLIENT),
        user_id=uuid.uuid4(),
        provider_kind=ProviderKind.XRAY,
        provider_name="xray",
        protocol=protocol,
        client_id=CLIENT,
        email="u@x.io",
        inbound_tag="in",
        host="1.2.3.4",
        port=443,
        expires_at=None,
        traffic_limit_bytes=None,
        settings=settings,
    )


def _params(uri: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(uri).query).items()}


def test_vless_tcp_none_defaults():
    uri = SubscriptionRenderer().render_config(_cfg("vless")).uri
    params = _params(uri)
    assert uri.startswith("vless://")
    assert params["type"] == "tcp"
    assert params["security"] == "none"


def test_vless_ws_tls_params():
    uri = (
        SubscriptionRenderer()
        .render_config(
            _cfg(
                "vless",
                network="ws",
                path="/ray",
                host="cdn.x.io",
                security="tls",
                sni="cdn.x.io",
                fingerprint="chrome",
            )
        )
        .uri
    )
    params = _params(uri)
    assert params["type"] == "ws"
    assert params["security"] == "tls"
    assert params["path"] == "/ray"
    assert params["host"] == "cdn.x.io"
    assert params["sni"] == "cdn.x.io"
    assert params["fp"] == "chrome"


def test_vless_grpc_reality_params():
    uri = (
        SubscriptionRenderer()
        .render_config(
            _cfg(
                "vless",
                network="grpc",
                serviceName="gun",
                security="reality",
                sni="apple.com",
                publicKey="PBK",
                shortId="ab12",
                fingerprint="chrome",
            )
        )
        .uri
    )
    params = _params(uri)
    assert params["type"] == "grpc"
    assert params["security"] == "reality"
    assert params["serviceName"] == "gun"
    assert params["pbk"] == "PBK"
    assert params["sid"] == "ab12"
    assert params["sni"] == "apple.com"


def test_vless_httpupgrade_params():
    uri = (
        SubscriptionRenderer()
        .render_config(
            _cfg(
                "vless",
                network="httpupgrade",
                path="/up",
                host="h.x.io",
                security="tls",
                sni="h.x.io",
            )
        )
        .uri
    )
    params = _params(uri)
    assert params["type"] == "httpupgrade"
    assert params["path"] == "/up"
    assert params["host"] == "h.x.io"


def test_trojan_ws_tls_params():
    uri = (
        SubscriptionRenderer()
        .render_config(
            _cfg("trojan", network="ws", path="/t", host="t.io", security="tls", sni="t.io")
        )
        .uri
    )
    params = _params(uri)
    assert uri.startswith("trojan://")
    assert params["type"] == "ws"
    assert params["security"] == "tls"
    assert params["path"] == "/t"


def test_vmess_transport_fields_in_base64():
    uri = (
        SubscriptionRenderer()
        .render_config(
            _cfg(
                "vmess",
                network="ws",
                path="/v",
                host="h.io",
                security="tls",
                sni="h.io",
                fingerprint="firefox",
            )
        )
        .uri
    )
    assert uri.startswith("vmess://")
    data = json.loads(base64.b64decode(uri.removeprefix("vmess://")))
    assert data["net"] == "ws"
    assert data["path"] == "/v"
    assert data["tls"] == "tls"
    assert data["sni"] == "h.io"
    assert data["fp"] == "firefox"


def test_vmess_grpc_service_name():
    uri = (
        SubscriptionRenderer().render_config(_cfg("vmess", network="grpc", serviceName="gsvc")).uri
    )
    data = json.loads(base64.b64decode(uri.removeprefix("vmess://")))
    assert data["net"] == "grpc"
    assert data["path"] == "gsvc"


def test_reality_tls_flag_in_vmess():
    uri = (
        SubscriptionRenderer()
        .render_config(_cfg("vmess", network="tcp", security="reality", sni="x.io", publicKey="k"))
        .uri
    )
    data = json.loads(base64.b64decode(uri.removeprefix("vmess://")))
    assert data["tls"] == "tls"
