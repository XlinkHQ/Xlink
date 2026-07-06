from __future__ import annotations

from collections.abc import Callable

from app.subscription.formats import base64 as base64_format
from app.subscription.formats import (
    clash,
    http_proxy,
    hysteria2,
    mihomo,
    naive,
    shadowsocks,
    singbox,
    socks,
    text,
    trojan,
    tuic,
    vless,
    vmess,
    wireguard,
    xray_json,
)
from app.subscription.formats.base import FormatRenderError
from app.subscription.models import ProviderConfig
from app.subscription.schemas import SubscriptionFormat

FeedRenderFn = Callable[[tuple[ProviderConfig, ...]], str]


def _single_protocol_feed(
    render_one: Callable[[ProviderConfig], str], protocol: str | tuple[str, ...]
) -> FeedRenderFn:
    protocols = (protocol,) if isinstance(protocol, str) else protocol

    def _render(configs: tuple[ProviderConfig, ...]) -> str:
        matching = [c for c in configs if c.protocol in protocols]
        if not matching:
            raise FormatRenderError(
                f"No '{'/'.join(protocols)}' configs available for this format.",
                code="subscription_format_incompatible",
                details={"protocol": protocols[0]},
            )
        return "\n".join(render_one(c) for c in matching)

    return _render


class RendererRegistry:
    def __init__(self) -> None:
        self._renderers: dict[SubscriptionFormat, FeedRenderFn] = {}

    def register(self, fmt: SubscriptionFormat, renderer: FeedRenderFn) -> None:
        self._renderers[fmt] = renderer

    def get(self, fmt: SubscriptionFormat) -> FeedRenderFn:
        renderer = self._renderers.get(fmt)
        if renderer is None:
            raise FormatRenderError(
                f"No renderer registered for format '{fmt.value}'.",
                code="subscription_format_unsupported",
                details={"format": fmt.value},
            )
        return renderer

    def render(self, fmt: SubscriptionFormat, configs: tuple[ProviderConfig, ...]) -> str:
        return self.get(fmt)(configs)

    def formats(self) -> frozenset[SubscriptionFormat]:
        return frozenset(self._renderers)


def default_registry() -> RendererRegistry:
    registry = RendererRegistry()
    registry.register(SubscriptionFormat.TEXT, text.render)
    registry.register(SubscriptionFormat.BASE64, base64_format.render)
    registry.register(SubscriptionFormat.XRAY_JSON, xray_json.render)
    registry.register(SubscriptionFormat.SINGBOX_JSON, singbox.render)
    registry.register(SubscriptionFormat.CLASH_YAML, clash.render)
    registry.register(SubscriptionFormat.MIHOMO_YAML, mihomo.render)
    registry.register(SubscriptionFormat.WIREGUARD_CONF, wireguard.render)
    registry.register(
        SubscriptionFormat.VLESS_URI, _single_protocol_feed(vless.render, vless.PROTOCOL)
    )
    registry.register(
        SubscriptionFormat.VMESS_URI, _single_protocol_feed(vmess.render, vmess.PROTOCOL)
    )
    registry.register(
        SubscriptionFormat.TROJAN_URI, _single_protocol_feed(trojan.render, trojan.PROTOCOL)
    )
    registry.register(
        SubscriptionFormat.SHADOWSOCKS_URI,
        _single_protocol_feed(shadowsocks.render, shadowsocks.PROTOCOLS),
    )
    registry.register(
        SubscriptionFormat.HYSTERIA2_URI,
        _single_protocol_feed(hysteria2.render, hysteria2.PROTOCOL),
    )
    registry.register(
        SubscriptionFormat.TUIC_URI, _single_protocol_feed(tuic.render, tuic.PROTOCOL)
    )
    registry.register(
        SubscriptionFormat.SOCKS_URI, _single_protocol_feed(socks.render, socks.PROTOCOL)
    )
    registry.register(
        SubscriptionFormat.HTTP_URI, _single_protocol_feed(http_proxy.render, http_proxy.PROTOCOL)
    )
    registry.register(
        SubscriptionFormat.NAIVE_URI, _single_protocol_feed(naive.render, naive.PROTOCOL)
    )
    return registry
