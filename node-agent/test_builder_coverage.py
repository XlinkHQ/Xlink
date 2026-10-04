"""Builder-level drift guard.

`app/subscription/tests/test_protocol_source.py` mirrors the protocol NAME
lists across every surface, including this agent's `CORE_PROTOCOLS`. What it
cannot see is whether a builder actually has a branch for each name it claims
to support, or whether the field keys a builder READS match the keys the panel
WRITES.

That gap let `shadowsocks2022` be routed to the xray builder with no xray
branch: the emitted inbound carries `protocol: "shadowsocks2022"`, which xray
has no such protocol for, so `xray run -test` rejects the file and the agent
keeps the PREVIOUS config — freezing updates for every user on the node, not
just the one with that protocol.
"""

import importlib.util
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("agent_mod", os.path.join(_HERE, "xlink-agent.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# Protocol names xray itself understands as inbound `protocol` values.
_XRAY_REAL_PROTOCOLS = {
    "vless", "vmess", "trojan", "shadowsocks", "socks", "http", "dokodemo-door",
}


def _user_inbounds(cfg):
    """Client-facing inbounds only — build_xray_config also emits the local
    dokodemo-door API inbound, which is not under test."""
    return [ib for ib in cfg.get("inbounds", []) if ib.get("tag") != "api"]


def _client(protocol, **settings):
    base = {"port": 443, "network": "tcp"}
    base.update(settings)
    return {
        "assignment_id": "11111111-1111-1111-1111-111111111111",
        "client_id": "22222222-2222-2222-2222-222222222222",
        "provider_kind": "xray",
        "protocol": protocol,
        "settings": base,
        "credentials": {},
    }


@pytest.mark.parametrize("protocol", sorted(m.CORE_PROTOCOLS["xray"]))
def test_xray_builder_emits_a_protocol_xray_understands(protocol):
    """Every protocol routed to xray must produce an inbound xray can parse."""
    cfg = m.build_xray_config([_client(protocol)])
    inbounds = _user_inbounds(cfg)
    assert inbounds, f"{protocol}: builder produced no inbound at all"
    emitted = {ib.get("protocol") for ib in inbounds}
    unknown = emitted - _XRAY_REAL_PROTOCOLS
    assert not unknown, (
        f"{protocol}: builder emitted inbound protocol(s) {unknown} that xray does not "
        f"implement. xray run -test will reject the config and the agent will keep the "
        f"PREVIOUS config, freezing updates for every user on this node."
    )


def test_shadowsocks2022_carries_a_method():
    """ss2022 needs its AEAD method on the inbound, like plain shadowsocks does."""
    cfg = m.build_xray_config([_client("shadowsocks2022", method="2022-blake3-aes-256-gcm")])
    ib = _user_inbounds(cfg)[0]
    assert ib["settings"].get("method"), (
        "shadowsocks2022 inbound has no `method`; the server cannot agree on a cipher "
        "with the client the subscription renderer hands out."
    )


def test_singbox_grpc_reads_service_name_not_path():
    """The panel and every client renderer use `serviceName`; the agent must agree.

    gRPC service names must match byte-for-byte, so reading the wrong key means
    the tunnel connects and then carries no traffic.
    """
    t = m._singbox_transport({"network": "grpc", "serviceName": "mysvc", "path": "/wrong"})
    assert t["service_name"] == "mysvc", (
        f"agent read {t['service_name']!r} but the panel writes `serviceName` = 'mysvc'"
    )


def test_singbox_ws_keeps_the_host_header():
    """CDN-fronted ws profiles need the Host header the client sends."""
    t = m._singbox_transport({"network": "ws", "path": "/p", "host": "cdn.example.com"})
    headers = t.get("headers") or {}
    assert headers.get("Host") == "cdn.example.com", (
        "agent dropped the ws Host header; the subscription renderer sends it, so "
        "CDN-fronted profiles break on sing-box nodes."
    )


@pytest.mark.parametrize("mtu,expected", [(1280, True), (1420, True), (1500, True)])
def test_wireguard_emits_mtu_inside_the_supported_range(mtu, expected):
    conf = m.build_wireguard_config([{
        "settings": {
            "privateKey": "aGVsbG93b3JsZGhlbGxvd29ybGRoZWxsb3dvcmxkMTI=",
            "port": 51820, "address": "10.8.0.1/24", "mtu": mtu,
        },
        "credentials": {},
    }])
    assert (f"MTU = {mtu}" in conf) is expected
