"""The share-link / config parser is hand-written, takes operator-pasted text
from anywhere, and had no tests. These pin the shapes it must produce and,
just as importantly, that malformed input returns None instead of raising."""

from __future__ import annotations

import base64
import json

from app.api.v1.outbound_import import parse_import


def _vmess_link(payload: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"vmess://{raw}"


# --------------------------------------------------------------------------
# vless / trojan
# --------------------------------------------------------------------------


def test_vless_plain() -> None:
    out = parse_import("vless://uuid-1@example.com:443?encryption=none#tag")
    assert out == {
        "type": "vless",
        "settings": {"address": "example.com:443", "id": "uuid-1", "encryption": "none"},
    }


def test_vless_reality_carries_pbk_and_sid() -> None:
    link = (
        "vless://uuid-2@1.2.3.4:8443"
        "?security=reality&sni=www.example.org&fp=chrome&pbk=PUBKEY&sid=ab12&type=grpc"
        "&serviceName=svc&flow=xtls-rprx-vision"
    )
    s = parse_import(link)["settings"]
    assert s["address"] == "1.2.3.4:8443"
    assert s["security"] == "reality"
    assert s["publicKey"] == "PUBKEY"
    assert s["shortId"] == "ab12"
    assert s["sni"] == "www.example.org"
    assert s["fingerprint"] == "chrome"
    assert s["network"] == "grpc"
    assert s["serviceName"] == "svc"
    assert s["flow"] == "xtls-rprx-vision"


def test_vless_ws_path_is_url_decoded() -> None:
    s = parse_import("vless://u@h.example:443?type=ws&path=%2Fa%2Fb&host=cdn.example")["settings"]
    assert s["network"] == "ws"
    assert s["path"] == "/a/b"
    assert s["host"] == "cdn.example"


def test_trojan_uses_password_not_id() -> None:
    out = parse_import("trojan://s3cret@t.example:443#x")
    assert out["type"] == "trojan"
    assert out["settings"]["password"] == "s3cret"
    assert "id" not in out["settings"]


def test_vless_ipv6_host_keeps_brackets() -> None:
    s = parse_import("vless://u@[2001:db8::1]:443?encryption=none")["settings"]
    assert s["address"] == "[2001:db8::1]:443"


def test_percent_encoded_credential_is_decoded() -> None:
    s = parse_import("trojan://p%40ss%3Aword@h.example:443")["settings"]
    assert s["password"] == "p@ss:word"


def test_tcp_network_is_not_emitted() -> None:
    # tcp is the default; emitting it would add noise to every outbound.
    s = parse_import("vless://u@h.example:443?type=tcp&encryption=none")["settings"]
    assert "network" not in s


def test_unknown_security_is_dropped() -> None:
    s = parse_import("vless://u@h.example:443?security=bogus&sni=x")["settings"]
    assert "security" not in s
    assert "sni" not in s


# --------------------------------------------------------------------------
# vmess
# --------------------------------------------------------------------------


def test_vmess_basic() -> None:
    out = parse_import(_vmess_link({"add": "v.example", "port": 443, "id": "uuid-3"}))
    assert out["type"] == "vmess"
    assert out["settings"] == {"address": "v.example:443", "id": "uuid-3"}


def test_vmess_ws_tls() -> None:
    s = parse_import(
        _vmess_link(
            {
                "add": "v.example",
                "port": "8443",
                "id": "uuid-4",
                "net": "ws",
                "tls": "tls",
                "sni": "sni.example",
                "path": "/ws",
                "host": "cdn.example",
            }
        )
    )["settings"]
    assert s["network"] == "ws"
    assert s["security"] == "tls"
    assert s["sni"] == "sni.example"
    assert s["path"] == "/ws"
    assert s["host"] == "cdn.example"


def test_vmess_unpadded_base64_is_accepted() -> None:
    # Real-world share links routinely strip '=' padding.
    payload = json.dumps({"add": "p.example", "port": 443, "id": "uuid-5"}).encode()
    link = "vmess://" + base64.urlsafe_b64encode(payload).decode().rstrip("=")
    assert parse_import(link) is not None


def test_vmess_rejects_non_json_body() -> None:
    assert parse_import("vmess://" + base64.urlsafe_b64encode(b"not json").decode()) is None


def test_vmess_missing_id_is_rejected() -> None:
    assert parse_import(_vmess_link({"add": "v.example", "port": 443})) is None


# --------------------------------------------------------------------------
# shadowsocks — the trickiest format (two encodings in the wild)
# --------------------------------------------------------------------------


def test_ss_fully_base64_body() -> None:
    body = base64.urlsafe_b64encode(b"aes-256-gcm:pw@s.example:8388").decode().rstrip("=")
    out = parse_import(f"ss://{body}")
    assert out == {
        "type": "shadowsocks",
        "settings": {"address": "s.example:8388", "method": "aes-256-gcm", "password": "pw"},
    }


def test_ss_base64_userinfo_only() -> None:
    creds = base64.urlsafe_b64encode(b"chacha20-ietf-poly1305:pw2").decode().rstrip("=")
    s = parse_import(f"ss://{creds}@s2.example:443#label")["settings"]
    assert s["method"] == "chacha20-ietf-poly1305"
    assert s["password"] == "pw2"
    assert s["address"] == "s2.example:443"


def test_ss_plain_userinfo() -> None:
    s = parse_import("ss://aes-128-gcm:plainpw@s3.example:1080")["settings"]
    assert s["method"] == "aes-128-gcm"
    assert s["password"] == "plainpw"


def test_ss_password_containing_colon_is_preserved() -> None:
    s = parse_import("ss://aes-256-gcm:a:b:c@s.example:443")["settings"]
    assert s["password"] == "a:b:c"


def test_ss_fragment_is_stripped_before_parsing() -> None:
    s = parse_import("ss://aes-128-gcm:pw@s.example:443#my%20label")["settings"]
    assert s["address"] == "s.example:443"


def test_ss_without_method_separator_is_rejected() -> None:
    assert parse_import("ss://" + base64.urlsafe_b64encode(b"nomethod@h:1").decode()) is None


# --------------------------------------------------------------------------
# Xray config JSON
# --------------------------------------------------------------------------


def test_xray_config_skips_builtin_outbounds() -> None:
    doc = {
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole"},
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": "x.example",
                            "port": 443,
                            "users": [{"id": "uuid-6", "flow": "xtls-rprx-vision"}],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "grpc",
                    "security": "reality",
                    "realitySettings": {"serverName": "s.example", "publicKey": "PK"},
                },
            },
        ]
    }
    out = parse_import(json.dumps(doc))
    assert out["type"] == "vless"
    s = out["settings"]
    assert s["address"] == "x.example:443"
    assert s["id"] == "uuid-6"
    assert s["flow"] == "xtls-rprx-vision"
    assert s["security"] == "reality"
    assert s["publicKey"] == "PK"
    assert s["sni"] == "s.example"


def test_xray_bare_outbound_object() -> None:
    doc = {
        "protocol": "trojan",
        "settings": {"servers": [{"address": "t.example", "port": 443, "password": "pw"}]},
    }
    out = parse_import(json.dumps(doc))
    assert out["type"] == "trojan"
    assert out["settings"] == {"address": "t.example:443", "password": "pw"}


def test_xray_shadowsocks_server_entry() -> None:
    doc = {
        "protocol": "shadowsocks",
        "settings": {
            "servers": [
                {"address": "s.example", "port": 8388, "method": "aes-256-gcm", "password": "pw"}
            ]
        },
    }
    s = parse_import(json.dumps(doc))["settings"]
    assert s == {"address": "s.example:8388", "method": "aes-256-gcm", "password": "pw"}


def test_xray_config_with_only_builtins_yields_nothing() -> None:
    doc = {"outbounds": [{"protocol": "freedom"}, {"protocol": "dns"}]}
    assert parse_import(json.dumps(doc)) is None


def test_xray_vless_without_user_id_is_rejected() -> None:
    doc = {
        "protocol": "vless",
        "settings": {"vnext": [{"address": "x.example", "port": 443, "users": [{}]}]},
    }
    assert parse_import(json.dumps(doc)) is None


# --------------------------------------------------------------------------
# Malformed input must return None, never raise
# --------------------------------------------------------------------------


def test_empty_and_whitespace() -> None:
    assert parse_import("") is None
    assert parse_import("   \n  ") is None


def test_unknown_scheme() -> None:
    assert parse_import("https://example.com") is None
    assert parse_import("just some text") is None


def test_broken_json() -> None:
    assert parse_import('{"outbounds": [') is None


def test_json_array_at_top_level_is_not_a_config() -> None:
    # starts with '[' so it is not treated as JSON at all -> no crash
    assert parse_import("[1,2,3]") is None


def test_missing_host_or_port_is_rejected() -> None:
    assert parse_import("vless://uuid@:443") is None
    assert parse_import("vless://uuid@example.com") is None
    assert parse_import("vless://@example.com:443") is None


def test_garbage_after_scheme_does_not_raise() -> None:
    for bad in (
        "vmess://",
        "ss://",
        "vless://",
        "trojan://",
        "vmess://!!!not-base64!!!",
        "ss://@@@",
        "vless://u@h.example:notaport?x=1",
    ):
        parse_import(bad)  # must not raise


def test_scheme_matching_is_case_insensitive() -> None:
    assert parse_import("VLESS://u@h.example:443?encryption=none") is not None


def test_very_long_input_is_handled() -> None:
    # `text` has no max length on the request schema, so the parser must not
    # blow up on a large paste.
    assert parse_import("vless://u@h.example:443?path=" + "a" * 100_000) is not None
    assert parse_import("x" * 500_000) is None
