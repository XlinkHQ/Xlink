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

The matrix must match what the renderers actually emit today (verified by
``test_capability_matrix.py``). It is NOT a place to change behaviour: adding a
protocol here without teaching the renderer to emit it, or vice versa, is a bug
the parity test will catch.
"""

from __future__ import annotations

from app.subscription.schemas import SubscriptionFormat

# --- Building blocks -------------------------------------------------------

# Every protocol that has a single-line URI form (vless://, ss://, wg://...).
# Drives TEXT, BASE64 and the URI family. shadowtls has NO URI form (it is a
# transport wrapper), so it is intentionally absent here.
_URI_PROTOCOLS = frozenset(
    {
        "vless",
        "vmess",
        "trojan",
        "shadowsocks",
        "shadowsocks2022",
        "hysteria2",
        "tuic",
        "socks",
        "http",
        "naive",
        "wireguard",
    }
)

# Clash core (stash / original clash) only understands these proxy types.
_CLASH_PROTOCOLS = frozenset(
    {
        "vless",
        "vmess",
        "trojan",
        "shadowsocks",
        "shadowsocks2022",
    }
)

# Clash.Meta / mihomo adds the QUIC-based and proxy protocols plus shadowtls.
_MIHOMO_PROTOCOLS = _CLASH_PROTOCOLS | frozenset(
    {"hysteria2", "tuic", "socks", "http", "shadowtls"}
)

# xray_json emits only the classic V2Ray outbounds.
_XRAY_JSON_PROTOCOLS = frozenset({"vless", "vmess", "trojan"})

# sing-box outbounds: everything Clash.Meta carries EXCEPT it has no wireguard
# or naive outbound in this feed, and it does support shadowtls (as a paired
# shadowtls+shadowsocks outbound).
_SINGBOX_PROTOCOLS = frozenset(
    {
        "vless",
        "vmess",
        "trojan",
        "shadowsocks",
        "shadowsocks2022",
        "hysteria2",
        "tuic",
        "socks",
        "http",
        "shadowtls",
    }
)


# --- The matrix ------------------------------------------------------------

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
