from __future__ import annotations

import pytest

from app.providers.base.models import ClientSpec
from app.providers.xray.adapter import build_create_client_payload
from app.providers.xray.exceptions import (
    InvalidStreamSettingsError,
    UnsupportedNetworkError,
    UnsupportedSecurityError,
)
from app.providers.xray.stream import build_stream_settings

VALID_UUID = "11111111-1111-1111-1111-111111111111"


def _spec(protocol="vless", **attrs):
    return ClientSpec(
        client_id=VALID_UUID, email="u@x.io", attributes={"protocol": protocol, **attrs}
    )


def test_default_transport_is_tcp_none():
    stream = build_stream_settings({})
    assert stream["network"] == "tcp"
    assert stream["security"] == "none"
    assert stream["tcpSettings"]["header"]["type"] == "none"


def test_ws_transport_settings():
    stream = build_stream_settings({"network": "ws", "path": "/ray", "host": "cdn.x.io"})
    assert stream["network"] == "ws"
    assert stream["wsSettings"]["path"] == "/ray"
    assert stream["wsSettings"]["headers"]["Host"] == "cdn.x.io"


def test_grpc_transport_settings():
    stream = build_stream_settings({"network": "grpc", "serviceName": "gun", "multiMode": True})
    assert stream["grpcSettings"]["serviceName"] == "gun"
    assert stream["grpcSettings"]["multiMode"] is True


def test_httpupgrade_transport_settings():
    stream = build_stream_settings({"network": "httpupgrade", "path": "/up", "host": "h.x.io"})
    assert stream["httpupgradeSettings"]["path"] == "/up"
    assert stream["httpupgradeSettings"]["host"] == "h.x.io"


def test_tls_security_settings():
    stream = build_stream_settings(
        {"network": "ws", "security": "tls", "sni": "x.io", "alpn": "h2,http/1.1"}
    )
    assert stream["security"] == "tls"
    assert stream["tlsSettings"]["serverName"] == "x.io"
    assert stream["tlsSettings"]["alpn"] == ["h2", "http/1.1"]


def test_reality_security_settings():
    stream = build_stream_settings(
        {
            "network": "tcp",
            "security": "reality",
            "sni": "apple.com",
            "publicKey": "PBK",
            "shortId": "ab12",
        }
    )
    assert stream["security"] == "reality"
    assert stream["realitySettings"]["publicKey"] == "PBK"
    assert stream["realitySettings"]["shortId"] == "ab12"
    assert stream["realitySettings"]["serverName"] == "apple.com"


def test_unsupported_network_rejected():
    with pytest.raises(UnsupportedNetworkError):
        build_stream_settings({"network": "kcp"})


def test_unsupported_security_rejected():
    with pytest.raises(UnsupportedSecurityError):
        build_stream_settings({"security": "xtls"})


def test_tls_requires_sni():
    with pytest.raises(InvalidStreamSettingsError):
        build_stream_settings({"network": "tcp", "security": "tls"})


def test_reality_requires_publickey():
    with pytest.raises(InvalidStreamSettingsError):
        build_stream_settings({"network": "tcp", "security": "reality", "sni": "x.io"})


def test_reality_requires_sni():
    with pytest.raises(InvalidStreamSettingsError):
        build_stream_settings({"network": "tcp", "security": "reality", "publicKey": "k"})


def test_reality_rejected_on_ws():
    with pytest.raises(InvalidStreamSettingsError):
        build_stream_settings(
            {"network": "ws", "security": "reality", "sni": "x.io", "publicKey": "k"}
        )


def test_reality_allowed_on_grpc():
    stream = build_stream_settings(
        {"network": "grpc", "security": "reality", "sni": "x.io", "publicKey": "k"}
    )
    assert stream["security"] == "reality"


def test_payload_includes_stream_settings():
    payload = build_create_client_payload(
        _spec("vless", network="ws", path="/p", security="tls", sni="x.io")
    )
    assert payload["streamSettings"]["network"] == "ws"
    assert payload["streamSettings"]["security"] == "tls"


def test_reality_requires_vless_protocol():
    with pytest.raises(InvalidStreamSettingsError):
        build_create_client_payload(
            _spec("vmess", network="tcp", security="reality", sni="x.io", publicKey="k")
        )


def test_reality_with_trojan_rejected():
    with pytest.raises(InvalidStreamSettingsError):
        build_create_client_payload(
            _spec("trojan", network="tcp", security="reality", sni="x.io", publicKey="k")
        )


def test_all_transport_security_matrix():
    networks = ["tcp", "ws", "grpc", "httpupgrade"]
    for network in networks:
        extra = {"serviceName": "s"} if network == "grpc" else {"path": "/p", "host": "h"}
        none_payload = build_create_client_payload(_spec("vless", network=network, **extra))
        assert none_payload["streamSettings"]["network"] == network
        tls_payload = build_create_client_payload(
            _spec("vless", network=network, security="tls", sni="x.io", **extra)
        )
        assert tls_payload["streamSettings"]["security"] == "tls"
