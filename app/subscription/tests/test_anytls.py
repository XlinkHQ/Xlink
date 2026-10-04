"""AnyTLS end to end: server inbound, URI, sing-box and Mihomo outbounds agree."""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import yaml

from app.providers.base.models import ProviderKind
from app.subscription.formats import anytls, mihomo, singbox
from app.subscription.models import ProviderConfig

_AGENT = Path(__file__).resolve().parents[3] / "node-agent" / "xlink-agent.py"
_spec = importlib.util.spec_from_file_location("agent_anytls", _AGENT)
agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agent)


def _config(**settings) -> ProviderConfig:
    base = {"password": "s3cret", "sni": "cdn.example.com", "port": 8443}
    base.update(settings)
    return ProviderConfig(
        assignment_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider_kind=ProviderKind.SING_BOX,
        provider_name="sing-box",
        protocol="anytls",
        client_id="cid-1",
        email=None,
        inbound_tag="anytls-in",
        host="vpn.example.com",
        port=8443,
        expires_at=None,
        traffic_limit_bytes=None,
        settings=base,
    )


def test_uri_shape() -> None:
    u = urlparse(anytls.render(_config()))
    assert u.scheme == "anytls"
    assert unquote(u.username or "") == "s3cret"
    assert u.hostname == "vpn.example.com" and u.port == 8443
    assert parse_qs(u.query)["sni"] == ["cdn.example.com"]


def test_uri_falls_back_to_host_for_sni() -> None:
    cfg = _config()
    cfg.settings.pop("sni")  # type: ignore[attr-defined]
    assert parse_qs(urlparse(anytls.render(cfg)).query)["sni"] == ["vpn.example.com"]


def test_singbox_outbound_has_mandatory_tls() -> None:
    out = json.loads(singbox.render((_config(),)))
    ob = next(o for o in out["outbounds"] if o.get("type") == "anytls")
    assert ob["password"] == "s3cret"
    assert ob["tls"]["enabled"] is True
    assert ob["tls"]["server_name"] == "cdn.example.com"


def test_mihomo_proxy() -> None:
    doc = yaml.safe_load(mihomo.render((_config(),)))
    proxy = next(p for p in doc["proxies"] if p["type"] == "anytls")
    assert proxy["password"] == "s3cret"
    assert proxy["sni"] == "cdn.example.com"


def test_agent_inbound_is_anytls_with_tls_and_user() -> None:
    cfg = agent.build_singbox_config([
        {
            "assignment_id": "a1",
            "client_id": "cid-1",
            "provider_kind": "sing-box",
            "protocol": "anytls",
            "settings": {"port": 8443, "security": "tls", "sni": "cdn.example.com"},
            "credentials": {},
        }
    ])
    ib = next(i for i in cfg["inbounds"] if i.get("type") == "anytls")
    assert ib["listen_port"] == 8443
    assert "tls" in ib, "sing-box rejects an anytls inbound without tls"
    assert ib["users"] and ib["users"][0]["password"]


def test_agent_forces_tls_even_without_security_setting() -> None:
    cfg = agent.build_singbox_config([
        {
            "assignment_id": "a2",
            "client_id": "cid-2",
            "provider_kind": "sing-box",
            "protocol": "anytls",
            "settings": {"port": 9443},
            "credentials": {},
        }
    ])
    ib = next(i for i in cfg["inbounds"] if i.get("type") == "anytls")
    assert "tls" in ib
