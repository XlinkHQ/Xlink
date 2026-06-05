from __future__ import annotations

from app.subscription.formats.uri import render_uri
from app.subscription.models import ProviderConfig


def render(configs: tuple[ProviderConfig, ...]) -> str:
    return "\n".join(render_uri(config) for config in configs)
