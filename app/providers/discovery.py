from __future__ import annotations

from app.providers.base.provider import Provider
from app.providers.base.registry import ProviderRegistry
from app.providers.hysteria.provider import HysteriaProvider
from app.providers.singbox.provider import SingBoxProvider
from app.providers.wireguard.provider import WireGuardProvider
from app.providers.xray.provider import XrayProvider


def default_providers() -> list[Provider]:
    return [
        XrayProvider(),
        WireGuardProvider(),
        SingBoxProvider(),
        HysteriaProvider(),
    ]


def build_registry(plugins_dir: str | None = None) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.discover(default_providers())
    from app.providers.plugins import register_plugins

    register_plugins(registry, plugins_dir)
    return registry
