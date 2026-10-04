"""Single source of truth for which protocols each subscription FORMAT can carry.

Historically every renderer carried its own protocol allow/deny set
(``xray_json`` filtered inline to vless/vmess/trojan, ``clash`` kept
``CLASH_PROTOCOLS``, ``mihomo`` kept ``MIHOMO_PROTOCOLS``, ``uri``/``text`` keyed
off ``URI_PROTOCOLS``, and the single-protocol URI feeds each pinned one
protocol). That knowledge was duplicated 5+ places and drifted silently: a
protocol a format structurally can't render was dropped by a blanket
``except FormatRenderError: continue`` with no signal to the caller.

This module centralises the protocol x format matrix so the renderers derive
their allow-sets from here, and so ``render_feed`` can compute *structural*
drops up front and LOG them instead of swallowing them.

The *set of protocols that exist at all* is defined once in ``app.protocols``;
this matrix says which of those each FORMAT can carry. ``test_protocol_source``
asserts every protocol named in this matrix is a known protocol there, and that
every subscription protocol there is carried by at least one format here.

The matrix must match what the renderers actually emit today (verified by
``test_capability_matrix.py``). It is NOT a place to change behaviour: adding a
protocol here without teaching the renderer to emit it, or vice versa, is a bug
the parity test will catch.
"""

from __future__ import annotations

from app.subscription.schemas import SubscriptionFormat

_URI_PROTOCOLS = frozenset(
    {
        "vless",
        "vmess",
        "trojan",
        "shadowsocks",
        "shadowsocks2022",
        "hysteria2",
        "tuic",
        "anytls",
        "socks",
        "http",
        "naive",
        "wireguard",
        "mtproto",
    }
)

_CLASH_PROTOCOLS = frozenset(
    {
        "vless",
        "vmess",
        "trojan",
        "shadowsocks",
        "shadowsocks2022",
    }
)

_MIHOMO_PROTOCOLS = _CLASH_PROTOCOLS | frozenset(
    {"hysteria2", "tuic", "anytls", "socks", "http", "shadowtls"}
)

_XRAY_JSON_PROTOCOLS = frozenset({"vless", "vmess", "trojan"})

_SINGBOX_PROTOCOLS = frozenset(
    {
        "vless",
        "vmess",
        "trojan",
        "shadowsocks",
        "shadowsocks2022",
        "hysteria2",
        "tuic",
        "anytls",
        "socks",
        "http",
        "shadowtls",
    }
)


FORMAT_PROTOCOLS: dict[SubscriptionFormat, frozenset[str]] = {
    SubscriptionFormat.TEXT: _URI_PROTOCOLS,
    SubscriptionFormat.BASE64: _URI_PROTOCOLS,
    SubscriptionFormat.XRAY_JSON: _XRAY_JSON_PROTOCOLS,
    SubscriptionFormat.SINGBOX_JSON: _SINGBOX_PROTOCOLS,
    SubscriptionFormat.CLASH_YAML: _CLASH_PROTOCOLS,
    SubscriptionFormat.MIHOMO_YAML: _MIHOMO_PROTOCOLS,
    SubscriptionFormat.WIREGUARD_CONF: frozenset({"wireguard"}),
    SubscriptionFormat.VLESS_URI: frozenset({"vless"}),
    SubscriptionFormat.VMESS_URI: frozenset({"vmess"}),
    SubscriptionFormat.TROJAN_URI: frozenset({"trojan"}),
    SubscriptionFormat.SHADOWSOCKS_URI: frozenset({"shadowsocks", "shadowsocks2022"}),
    SubscriptionFormat.HYSTERIA2_URI: frozenset({"hysteria2"}),
    SubscriptionFormat.TUIC_URI: frozenset({"tuic"}),
    SubscriptionFormat.SOCKS_URI: frozenset({"socks"}),
    SubscriptionFormat.HTTP_URI: frozenset({"http"}),
    SubscriptionFormat.NAIVE_URI: frozenset({"naive"}),
}


def supported_protocols(fmt: SubscriptionFormat) -> frozenset[str]:
    """Protocols the given format can structurally render."""
    return FORMAT_PROTOCOLS.get(fmt, frozenset())


def format_supports(fmt: SubscriptionFormat, protocol: str) -> bool:
    """True if ``protocol`` can appear in a feed rendered as ``fmt``."""
    return protocol in supported_protocols(fmt)
