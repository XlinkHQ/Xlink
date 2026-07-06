from __future__ import annotations

from app.core.logging import get_logger
from app.subscription.formats import wireguard
from app.subscription.formats.uri import URI_PROTOCOLS, render_uri
from app.subscription.models import ProviderConfig

logger = get_logger("xlink.subscription.text")


def render(configs: tuple[ProviderConfig, ...]) -> str:
    lines: list[str] = []
    for c in configs:
        if c.protocol in URI_PROTOCOLS:
            try:
                lines.append(render_uri(c))
            except Exception:
                logger.debug("text_render_skip", protocol=c.protocol, exc_info=True)
                continue
        elif c.protocol == wireguard.PROTOCOL:
            try:
                lines.append(wireguard.render_one(c))
            except Exception:
                logger.debug("text_render_skip", protocol=c.protocol, exc_info=True)
                continue
    return "\n".join(lines)
