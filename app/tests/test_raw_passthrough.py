"""Passthrough: operator JSON reaches the core/client verbatim, but the panel's
managed fields (identity, socket, users, credentials) can never be overridden."""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest

from app.core.exceptions import ValidationError
from app.providers.base.models import ProviderKind
from app.providers.settings_validation import validate_profile_settings
from app.subscription.formats import singbox, xray_json
from app.subscription.models import ProviderConfig

_AGENT = Path(__file__).resolve().parents[2] / "node-agent" / "xlink-agent.py"
_spec = importlib.util.spec_from_file_location("agent_raw", _AGENT)
agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agent)


def _client(protocol: str, **settings):
    return {
        "assignment_id": "a1",
        "client_id": "11111111-1111-1111-1111-111111111111",
        "provider_kind": "xray",
        "protocol": protocol,
        "settings": {"port": 443, "network": "tcp", **settings},
        "credentials": {},
    }


# ---------------------------------------------------------------- server side

def test_xray_raw_inbound_adds_a_field_the_panel_does_not_model() -> None:
    cfg = agent.build_xray_config([_client("vless", rawInbound={"sniffing": {"routeOnly": True}})])
    ib = next(i for i in cfg["inbounds"] if i.get("tag") != "api")
    assert ib["sniffing"]["routeOnly"] is True
    assert ib["sniffing"]["enabled"] is True, "deep merge must keep sibling keys"


def test_xray_raw_inbound_cannot_replace_port_or_clients() -> None:
    cfg = agent.build_xray_config(
        [_client("vless", rawInbound={"port": 1, "settings": {"decryption": "none"}, "tag": "x"})]
    )
    ib = next(i for i in cfg["inbounds"] if i.get("tag") != "api")
    assert ib["port"] == 443
    assert ib["tag"] != "x"
    assert ib["settings"]["clients"], "managed user list must survive"


def test_singbox_raw_inbound_merges() -> None:
    cfg = agent.build_singbox_config(
        [{**_client("vless", rawInbound={"tcp_fast_open": True}), "provider_kind": "sing-box"}]
    )
    ib = next(i for i in cfg["inbounds"] if i.get("type") == "vless")
    assert ib["tcp_fast_open"] is True
    assert ib["users"]


# ---------------------------------------------------------------- client side

def _cfg(protocol: str = "vless", **settings) -> ProviderConfig:
    return ProviderConfig(
        assignment_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider_kind=ProviderKind.XRAY,
        provider_name="xray",
        protocol=protocol,
        client_id=str(uuid.uuid4()),
        email=None,
        inbound_tag="t",
        host="vpn.example.com",
        port=443,
        expires_at=None,
        traffic_limit_bytes=None,
        settings={"security": "tls", "sni": "vpn.example.com", **settings},
    )


def test_singbox_client_outbound_passthrough() -> None:
    out = json.loads(singbox.render((_cfg(rawClientOutbound={"multiplex": {"enabled": True}}),)))
    ob = next(o for o in out["outbounds"] if o.get("type") == "vless")
    assert ob["multiplex"] == {"enabled": True}


def test_singbox_client_outbound_cannot_change_server_or_uuid() -> None:
    c = _cfg(rawClientOutbound={"server": "evil.example", "uuid": "x"})
    ob = next(o for o in json.loads(singbox.render((c,)))["outbounds"] if o.get("type") == "vless")
    assert ob["server"] == "vpn.example.com"
    assert ob["uuid"] == c.client_id


def test_xray_json_client_outbound_passthrough() -> None:
    cfg = _cfg(rawClientOutbound={"mux": {"enabled": True, "concurrency": 2}})
    doc = json.loads(xray_json.render((cfg,)))
    docs = doc if isinstance(doc, list) else [doc]
    proxy = next(o for d in docs for o in d["outbounds"] if o.get("protocol") == "vless")
    assert proxy["mux"]["concurrency"] == 2


# ---------------------------------------------------------------- save-time validation

@pytest.mark.parametrize("field", ["rawInbound", "rawClientOutbound"])
def test_non_object_is_rejected(field) -> None:
    with pytest.raises(ValidationError):
        validate_profile_settings(ProviderKind.XRAY, "vless", {field: "nope"})


def test_protected_key_is_rejected_at_save_not_silently_dropped() -> None:
    with pytest.raises(ValidationError, match="users"):
        validate_profile_settings(ProviderKind.XRAY, "vless", {"rawInbound": {"users": []}})


def test_oversized_override_is_rejected() -> None:
    with pytest.raises(ValidationError, match="too large"):
        validate_profile_settings(
            ProviderKind.XRAY, "vless", {"rawInbound": {"x": "a" * 20_000}}
        )


def test_valid_override_passes() -> None:
    validate_profile_settings(ProviderKind.XRAY, "vless", {"rawInbound": {"sniffing": {}}})
