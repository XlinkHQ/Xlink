from __future__ import annotations

from app.providers.base.provider import Provider
from app.providers.base.registry import ProviderRegistry
from app.providers.xray.provider import XrayProvider


def default_providers() -> list[Provider]:
    return [XrayProvider()]


def build_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.discover(default_providers())
    return registry
