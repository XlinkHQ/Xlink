from __future__ import annotations

from collections.abc import Callable

from app.subscription.formats import (
    anytls,
    http_proxy,
    hysteria2,
    naive,
    shadowsocks,
    socks,
    trojan,
    tuic,
    vless,
    vmess,
    wireguard,
)
from app.subscription.formats.base import FormatRenderError
from app.subscription.models import ProviderConfig

_URI_RENDERERS: dict[str, Callable[[ProviderConfig], str]] = {
    vless.PROTOCOL: vless.render,
    vmess.PROTOCOL: vmess.render,
    trojan.PROTOCOL: trojan.render,
    shadowsocks.PROTOCOL: shadowsocks.render,
    "shadowsocks2022": shadowsocks.render,
    hysteria2.PROTOCOL: hysteria2.render,
    tuic.PROTOCOL: tuic.render,
    anytls.PROTOCOL: anytls.render,
    socks.PROTOCOL: socks.render,
    http_proxy.PROTOCOL: http_proxy.render,
    naive.PROTOCOL: naive.render,
    wireguard.PROTOCOL: wireguard.render_one,
}

URI_PROTOCOLS = frozenset(_URI_RENDERERS)


def render_uri(config: ProviderConfig) -> str:
    renderer = _URI_RENDERERS.get(config.protocol)
    if renderer is None:
        raise FormatRenderError(
            f"Unsupported subscription protocol '{config.protocol}'.",
            code="subscription_protocol_unsupported",
            details={"protocol": config.protocol},
        )
    return renderer(config)
