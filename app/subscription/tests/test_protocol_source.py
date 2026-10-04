"""Drift guard for the single protocol source of truth (``app.protocols``).

Adding a protocol used to mean editing ~8-14 scattered lists; missing one
SILENTLY dropped the protocol. Now every panel-side list is DERIVED from
``app.protocols.PROTOCOLS`` and these tests assert the derived surfaces (and the
two separate-runtime mirrors that can't import it) all agree. A future addition
that misses a spot fails HERE, loudly, instead of dropping a protocol at
runtime.

Surfaces checked:
  * app.protocols.provider_protocols()            (source)
  * app.providers.base.models.PROVIDER_PROTOCOLS  (re-export, must be identical)
  * app.subscription.models.SUPPORTED_SUBSCRIPTION_PROTOCOLS (derived)
  * app.subscription.formats.uri.URI_PROTOCOLS    (renderer map)
  * app.subscription.formats.capabilities.FORMAT_PROTOCOLS (matrix)
  * the sing-box renderer dispatch                (rendered, not a dict)
  * node-agent CORE_PROTOCOLS                      (separate runtime, parsed)
  * web protocolsFor() PROVIDER_PROTOCOLS          (separate runtime, parsed)
"""

from __future__ import annotations

import ast
import re
import uuid
from pathlib import Path

import pytest

from app import protocols as source
from app.providers.base.models import PROVIDER_PROTOCOLS, ProviderKind
from app.providers.discovery import build_registry
from app.schemas.profile import VALID_PROTOCOLS
from app.subscription.formats import singbox
from app.subscription.formats.base import FormatRenderError
from app.subscription.formats.capabilities import (
    FORMAT_PROTOCOLS,
    supported_protocols,
)
from app.subscription.formats.uri import URI_PROTOCOLS
from app.subscription.models import (
    SUPPORTED_SUBSCRIPTION_PROTOCOLS,
    ProviderConfig,
)
from app.subscription.schemas import SubscriptionFormat

_REPO_ROOT = Path(__file__).resolve().parents[3]

_SETTINGS: dict[str, dict[str, object]] = {
    "vless": {"security": "tls", "sni": "x.io"},
    "vmess": {"security": "tls", "sni": "x.io"},
    "trojan": {"security": "tls", "sni": "x.io"},
    "shadowsocks": {"method": "aes-256-gcm", "password": "pw"},
    "shadowsocks2022": {"method": "2022-blake3-aes-256-gcm", "password": "pw"},
    "shadowtls": {"password": "pw", "sni": "x.io", "shadowtls_password": "st"},
    "hysteria2": {"password": "pw", "sni": "x.io"},
    "tuic": {"password": "pw", "sni": "x.io"},
    "anytls": {"password": "pw", "sni": "x.io"},
    "socks": {"username": "u", "password": "p"},
    "http": {"username": "u", "password": "p"},
    "naive": {"username": "u", "password": "p"},
    "wireguard": {"peerPublicKey": "PUB", "privateKey": "PRIV"},
}


def _cfg(protocol: str) -> ProviderConfig:
    return ProviderConfig(
        assignment_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider_kind=ProviderKind.XRAY,
        provider_name="xray",
        protocol=protocol,
        client_id="11111111-1111-1111-1111-111111111111",
        email="u@x.io",
        inbound_tag="in",
        host="1.2.3.4",
        port=443,
        expires_at=None,
        traffic_limit_bytes=None,
        settings=_SETTINGS[protocol],
    )


def test_provider_protocols_reexport_matches_source():
    """PROVIDER_PROTOCOLS (re-exported from providers.base.models) is exactly
    what the source derives; the re-export can't drift from app.protocols."""
    assert source.provider_protocols() == PROVIDER_PROTOCOLS


def test_provider_protocols_covers_every_kind():
    """Every ProviderKind has an entry (no core silently missing)."""
    assert set(PROVIDER_PROTOCOLS) == set(ProviderKind)


def test_protocols_for_matches_map():
    for kind in ProviderKind:
        assert source.protocols_for(kind) == PROVIDER_PROTOCOLS[kind]


def test_supported_subscription_protocols_is_derived():
    assert source.subscription_protocols() == SUPPORTED_SUBSCRIPTION_PROTOCOLS


def test_profile_valid_protocols_is_derived():
    """The profile schema's VALID_PROTOCOLS (what a profile may declare) equals
    the union of everything the providers can provision -- derived, not
    hand-listed."""
    provider_union = set().union(*PROVIDER_PROTOCOLS.values())
    assert provider_union == VALID_PROTOCOLS


def test_every_protocol_belongs_to_a_provider_or_is_http():
    """Every known protocol is provisioned by some provider, except ``http``
    which is subscription-only (rendered but not provisioned as an inbound).
    This pins the one deliberate exception so a new orphan protocol is noticed.
    """
    orphans = {spec.name for spec in source.PROTOCOLS if not spec.providers}
    assert orphans == {"http"}, f"protocols with no provider: {orphans} (only 'http' is expected)"


def test_provider_registry_only_offers_known_protocols():
    """Every protocol any registered provider claims to create is a known
    protocol AND matches the provider->protocol source."""
    registry = build_registry()
    known = source.all_protocols()
    for provider in registry.all():
        kind = provider.metadata.kind
        for protocol in PROVIDER_PROTOCOLS[kind]:
            assert protocol in known, f"{kind.value} offers unknown '{protocol}'"


def test_subscription_protocols_are_renderable_somewhere():
    """Every protocol the panel says it will put in a subscription must be
    carried by at least one FORMAT. A subscription protocol no format can render
    is a silent drop -- fail here instead."""
    carried = set().union(*FORMAT_PROTOCOLS.values())
    for protocol in SUPPORTED_SUBSCRIPTION_PROTOCOLS:
        assert protocol in carried, (
            f"'{protocol}' is a subscription protocol but no format carries it"
        )


def test_matrix_protocols_are_all_known():
    """Every protocol named anywhere in the format matrix is a defined
    protocol (no typo'd / stale name lurking in a format allow-set)."""
    known = source.all_protocols()
    for fmt, protos in FORMAT_PROTOCOLS.items():
        for protocol in protos:
            assert protocol in known, f"format {fmt.value} references unknown protocol '{protocol}'"


def test_uri_renderers_are_subscription_protocols():
    """Every protocol with a URI renderer is a known subscription protocol, and
    matches what the TEXT/BASE64 matrix rows claim."""
    known = source.all_protocols()
    for protocol in URI_PROTOCOLS:
        assert protocol in known, f"URI renderer for unknown '{protocol}'"
        assert protocol in SUPPORTED_SUBSCRIPTION_PROTOCOLS
    assert supported_protocols(SubscriptionFormat.TEXT) == URI_PROTOCOLS


def test_singbox_dispatch_matches_matrix():
    """The sing-box renderer (an if/elif chain, not a dict) must emit EXACTLY
    the protocols the matrix says the sing-box format carries -- rendering each
    known protocol and checking it produces an outbound iff the matrix claims
    support. This is the guard that a new sing-box protocol added to the matrix
    but not the dispatch (or vice versa) fails loudly."""
    import json

    sb_supported = supported_protocols(SubscriptionFormat.SINGBOX_JSON)
    for protocol in source.all_protocols():
        claims = protocol in sb_supported
        try:
            out = json.loads(singbox.render((_cfg(protocol),)))
            emitted = bool(out.get("outbounds"))
        except FormatRenderError:
            emitted = False
        assert emitted == claims, (
            f"sing-box dispatch/matrix disagree on '{protocol}': emitted={emitted} matrix={claims}"
        )


def _parse_node_agent_core_protocols() -> dict[str, frozenset[str]]:
    """Read CORE_PROTOCOLS out of node-agent/xlink-agent.py without importing
    it (it is a standalone daemon that would try to run on import)."""
    path = _REPO_ROOT / "node-agent" / "xlink-agent.py"
    src = path.read_text()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "CORE_PROTOCOLS":
                return {
                    ast.literal_eval(k): frozenset(_frozenset_arg(v))
                    for k, v in zip(node.value.keys, node.value.values, strict=True)
                }
    raise AssertionError("CORE_PROTOCOLS not found in node-agent/xlink-agent.py")


def _frozenset_arg(call: ast.expr) -> set[str]:
    assert isinstance(call, ast.Call), "expected frozenset(...) literal"
    (arg,) = call.args
    return set(ast.literal_eval(arg))


def _parse_web_provider_protocols() -> dict[str, frozenset[str]]:
    """Read PROVIDER_PROTOCOLS out of the web util.ts by regex (no JS runtime)."""
    path = _REPO_ROOT / "web" / "features" / "profiles" / "util.ts"
    src = path.read_text()
    block = re.search(
        r"const PROVIDER_PROTOCOLS[^=]*=\s*\{(.*?)\n\};",
        src,
        re.DOTALL,
    )
    assert block, "PROVIDER_PROTOCOLS not found in web util.ts"
    result: dict[str, frozenset[str]] = {}
    for m in re.finditer(r'("?)([\w-]+)\1\s*:\s*\[([^\]]*)\]', block.group(1)):
        key = m.group(2)
        vals = re.findall(r'"([^"]+)"', m.group(3))
        result[key] = frozenset(vals)
    return result


_KIND_KEY = {kind: kind.value for kind in ProviderKind}


def test_node_agent_mirror_matches_source():
    node = _parse_node_agent_core_protocols()
    for kind, protos in PROVIDER_PROTOCOLS.items():
        assert node.get(_KIND_KEY[kind]) == protos, (
            f"node-agent CORE_PROTOCOLS[{_KIND_KEY[kind]}] drifted from the "
            f"panel source: {node.get(_KIND_KEY[kind])} != {protos}"
        )
    assert set(node) == {_KIND_KEY[k] for k in ProviderKind}


def test_web_mirror_matches_source():
    web = _parse_web_provider_protocols()
    for kind, protos in PROVIDER_PROTOCOLS.items():
        assert web.get(_KIND_KEY[kind]) == protos, (
            f"web PROVIDER_PROTOCOLS[{_KIND_KEY[kind]}] drifted from the panel "
            f"source: {web.get(_KIND_KEY[kind])} != {protos}"
        )
    assert set(web) == {_KIND_KEY[k] for k in ProviderKind}


@pytest.mark.parametrize("protocol", sorted(_SETTINGS))
def test_settings_cover_every_known_protocol(protocol: str):
    """Meta: our test fixtures cover exactly the known protocols, so a new
    protocol forces the author through this file (and thus the guards)."""
    assert protocol in source.all_protocols()


def test_no_known_protocol_lacks_test_settings():
    assert source.all_protocols() == frozenset(_SETTINGS)
