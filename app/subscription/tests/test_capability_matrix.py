"""The capability matrix must match what the renderers actually emit today.

These tests are the guard that keeps ``formats/capabilities.py`` honest: if a
renderer starts (or stops) emitting a protocol, the matrix has to move with it,
otherwise ``render_feed`` would either log a phantom drop or — worse — silently
drop a protocol the matrix claims is supported.
"""

from __future__ import annotations

import json
import uuid

import pytest
import structlog
import yaml

from app.providers.base.models import ProviderKind
from app.subscription.formats.base import FormatRenderError
from app.subscription.formats.capabilities import (
    FORMAT_PROTOCOLS,
    supported_protocols,
)
from app.subscription.formats.clash import CLASH_PROTOCOLS, MIHOMO_PROTOCOLS
from app.subscription.formats.registry import default_registry
from app.subscription.formats.uri import URI_PROTOCOLS
from app.subscription.models import ProviderConfig
from app.subscription.renderer import SubscriptionRenderer
from app.subscription.schemas import SubscriptionFormat

CLIENT = "11111111-1111-1111-1111-111111111111"

# Per-protocol settings that let each renderer succeed on a valid node (so the
# only reason a protocol is missing from the output is the FORMAT rejecting it,
# never bad data).
_SETTINGS: dict[str, dict[str, object]] = {
    "vless": {"security": "tls", "sni": "x.io"},
    "vmess": {"security": "tls", "sni": "x.io"},
    "trojan": {"security": "tls", "sni": "x.io"},
    "shadowsocks": {"method": "aes-256-gcm", "password": "pw"},
    "shadowsocks2022": {"method": "2022-blake3-aes-256-gcm", "password": "pw"},
    "shadowtls": {"password": "pw", "sni": "x.io", "shadowtls_password": "st"},
    "hysteria2": {"password": "pw", "sni": "x.io"},
    "tuic": {"password": "pw", "sni": "x.io"},
    "socks": {"username": "u", "password": "p"},
    "http": {"username": "u", "password": "p"},
    "naive": {"username": "u", "password": "p"},
    "wireguard": {"peerPublicKey": "PUB", "privateKey": "PRIV"},
}

ALL_PROTOCOLS = frozenset(_SETTINGS)


def _cfg(protocol: str) -> ProviderConfig:
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
        settings=_SETTINGS[protocol],
    )


def _protocol_present(fmt: SubscriptionFormat, protocol: str, content: str) -> bool:
    """Did the rendered feed actually carry a proxy for ``protocol``?"""
    if not content.strip():
        return False
    if fmt in (SubscriptionFormat.CLASH_YAML, SubscriptionFormat.MIHOMO_YAML):
        doc = yaml.safe_load(content)
        return bool(doc.get("proxies"))
    if fmt in (SubscriptionFormat.XRAY_JSON, SubscriptionFormat.SINGBOX_JSON):
        doc = json.loads(content)
        items = doc if isinstance(doc, list) else doc.get("outbounds", [])
        # xray_json wraps each config in a full document; sing-box emits a flat
        # outbound list (plus direct/block for xray). Either way, a rendered
        # config means at least one non-empty entry.
        return bool(items)
    # text / base64 / wireguard_conf / *_uri: any content means it rendered.
    return bool(content.strip())


@pytest.mark.parametrize("fmt", list(SubscriptionFormat))
@pytest.mark.parametrize("protocol", sorted(ALL_PROTOCOLS))
def test_matrix_matches_renderer(fmt: SubscriptionFormat, protocol: str):
    """For every format x protocol: the matrix's claim must equal reality.

    - matrix says SUPPORTED  -> the renderer must actually emit it.
    - matrix says UNSUPPORTED -> the renderer must NOT emit it (drops it).
    No format may silently drop a protocol the matrix says it supports, and
    none may quietly emit one the matrix omits.
    """
    registry = default_registry()
    claims_support = protocol in supported_protocols(fmt)
    try:
        content = registry.render(fmt, (_cfg(protocol),))
    except FormatRenderError:
        # A hard rejection (single-protocol URI feed, "no compatible proxies").
        # That is a structural drop -> the matrix must NOT claim support.
        assert not claims_support, (
            f"{fmt.value} matrix claims '{protocol}' but the renderer raised "
            f"FormatRenderError (structural reject)"
        )
        return

    present = _protocol_present(fmt, protocol, content)
    assert present == claims_support, (
        f"{fmt.value}: matrix says support={claims_support} for '{protocol}' "
        f"but rendered-present={present}"
    )


def test_matrix_covers_every_format():
    """Every registered format has a matrix entry (no format falls through to
    the empty-set / silent branch by accident)."""
    registry_formats = default_registry().formats()
    assert registry_formats == frozenset(FORMAT_PROTOCOLS), (
        "registry formats and capability matrix keys diverged: "
        f"{registry_formats ^ frozenset(FORMAT_PROTOCOLS)}"
    )


def test_derived_module_constants_track_matrix():
    """The back-compat allow-sets left in the renderers are sourced from the
    matrix, not redefined — so they can never drift again."""
    assert CLASH_PROTOCOLS == FORMAT_PROTOCOLS[SubscriptionFormat.CLASH_YAML]
    assert MIHOMO_PROTOCOLS == FORMAT_PROTOCOLS[SubscriptionFormat.MIHOMO_YAML]
    assert URI_PROTOCOLS == FORMAT_PROTOCOLS[SubscriptionFormat.TEXT]
    assert URI_PROTOCOLS == FORMAT_PROTOCOLS[SubscriptionFormat.BASE64]


def test_dropped_protocol_is_logged():
    """A protocol the format can't carry is logged once per feed, not silently
    dropped."""
    renderer = SubscriptionRenderer()
    configs = (_cfg("wireguard"), _cfg("wireguard"), _cfg("wireguard"), _cfg("vless"))
    with structlog.testing.capture_logs() as logs:
        renderer.render_feed(configs, feed_format=SubscriptionFormat.CLASH_YAML)
    drops = [e for e in logs if e.get("event") == "subscription_feed_dropped"]
    assert len(drops) == 1, f"expected exactly one drop log, got {logs}"
    entry = drops[0]
    assert entry["format"] == "clash_yaml"
    assert entry["protocols"] == ["wireguard"]
    assert entry["count"] == 3


def test_no_drop_log_when_all_supported():
    """When every config is renderable by the format, nothing is logged."""
    renderer = SubscriptionRenderer()
    with structlog.testing.capture_logs() as logs:
        renderer.render_feed((_cfg("vless"),), feed_format=SubscriptionFormat.CLASH_YAML)
    assert not [e for e in logs if e.get("event") == "subscription_feed_dropped"]
