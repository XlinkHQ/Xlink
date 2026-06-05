from __future__ import annotations

from app.subscription.formats.clash import MIHOMO_PROTOCOLS, build_clash_document
from app.subscription.models import ProviderConfig


def render(configs: tuple[ProviderConfig, ...]) -> str:
    return build_clash_document(configs, allowed=MIHOMO_PROTOCOLS)
