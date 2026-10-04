"""Single authoritative definition of every proxy protocol XLink knows.

Adding a protocol used to mean editing ~8-14 scattered places (the provider
allow-sets, the subscription allow-set, the format capability matrix, the URI
renderer map, the sing-box dispatch, plus the node-agent and web mirrors) and
missing any one of them SILENTLY dropped the protocol. This module is the one
place a panel-side protocol fact lives; every panel constant that used to be
hand-maintained is now DERIVED from ``PROTOCOLS`` below, so they can't drift.

What still lives elsewhere (and why):

* ``app/subscription/formats/capabilities.py`` — the *format x protocol* matrix
  (which subscription FORMAT can carry which protocol). That is renderer
  knowledge, not protocol identity, so it stays there; a consistency test
  (``test_protocol_source.py``) asserts every subscription protocol here is
  covered by at least one format and every format-carried protocol is defined
  here.
* ``node-agent/xlink-agent.py`` and ``web/.../profiles/util.ts`` are SEPARATE
  runtimes (a standalone Python daemon and a TypeScript bundle) that cannot
  import this module. They keep their own lists, tagged with a pointer back
  here, and ``test_protocol_source.py`` reads both and asserts they match this
  source, so drift is caught in CI instead of at runtime.

ZERO behaviour change: the derived constants are byte-for-byte the same sets
that were hand-written before this consolidation (asserted by the tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.providers.base.models import ProviderKind


@dataclass(frozen=True)
class ProtocolSpec:
    """Everything the panel needs to know about one proxy protocol.

    Attributes:
        name: The canonical protocol identifier used everywhere (the ``protocol``
            string on a profile / ``ProviderConfig``).
        providers: Which provider cores can actually create a client for this
            protocol. Drives ``PROVIDER_PROTOCOLS`` / ``protocols_for``.
        subscription: Whether the panel will render this protocol into a user
            subscription. Drives ``SUPPORTED_SUBSCRIPTION_PROTOCOLS``.
    """

    name: str
    providers: frozenset[ProviderKind] = field(default_factory=frozenset)
    subscription: bool = True


def _spec(
    name: str,
    *,
    providers: tuple[ProviderKind, ...] = (),
    subscription: bool = True,
) -> ProtocolSpec:
    return ProtocolSpec(
        name=name,
        providers=frozenset(providers),
        subscription=subscription,
    )


XRAY = ProviderKind.XRAY
SING_BOX = ProviderKind.SING_BOX
HYSTERIA = ProviderKind.HYSTERIA
WIREGUARD = ProviderKind.WIREGUARD
MTPROTO = ProviderKind.MTPROTO

PROTOCOLS: tuple[ProtocolSpec, ...] = (
    _spec("vless", providers=(XRAY, SING_BOX)),
    _spec("vmess", providers=(XRAY, SING_BOX)),
    _spec("trojan", providers=(XRAY, SING_BOX)),
    _spec("shadowsocks", providers=(XRAY, SING_BOX)),
    _spec("shadowsocks2022", providers=(XRAY, SING_BOX)),
    _spec("shadowtls", providers=(SING_BOX,)),
    _spec("hysteria2", providers=(SING_BOX, HYSTERIA)),
    _spec("tuic", providers=(SING_BOX,)),
    # Padded-TLS transport built to defeat traffic-shape fingerprinting.
    _spec("anytls", providers=(SING_BOX,)),
    _spec("naive", providers=(SING_BOX,)),
    _spec("socks", providers=(SING_BOX,)),
    _spec("http", providers=()),
    _spec("wireguard", providers=(WIREGUARD,)),
    # Telegram proxy (fake-TLS). Feeds carry a t.me/proxy link.
    _spec("mtproto", providers=(MTPROTO,)),
)


_BY_NAME: dict[str, ProtocolSpec] = {spec.name: spec for spec in PROTOCOLS}


def all_protocols() -> frozenset[str]:
    """Every protocol name the panel knows about."""
    return frozenset(_BY_NAME)


def subscription_protocols() -> frozenset[str]:
    """Protocols the panel will render into a subscription feed."""
    return frozenset(spec.name for spec in PROTOCOLS if spec.subscription)


def provider_protocols() -> dict[ProviderKind, frozenset[str]]:
    """Which client protocols each provider core can create."""
    result: dict[ProviderKind, set[str]] = {kind: set() for kind in ProviderKind}
    for spec in PROTOCOLS:
        for kind in spec.providers:
            result[kind].add(spec.name)
    return {kind: frozenset(names) for kind, names in result.items()}


def protocols_for(kind: ProviderKind) -> frozenset[str]:
    """Client protocols a single provider ``kind`` can create."""
    return frozenset(spec.name for spec in PROTOCOLS if kind in spec.providers)
