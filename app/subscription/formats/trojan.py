from __future__ import annotations

from urllib.parse import quote

from app.subscription.formats.base import (
    label,
    query,
    require_fields,
    require_protocol,
    validate_node,
)
from app.subscription.formats.vless import transport_params
from app.subscription.models import ProviderConfig

PROTOCOL = "trojan"


def render(config: ProviderConfig) -> str:
    require_protocol(config, PROTOCOL)
    require_fields(config, ("client_id", "host", "port"))
    validate_node(config)
    return (
        f"trojan://{quote(config.resolved_password)}@{config.host}:{config.port}"
        f"?{query(transport_params(config))}#{label(config)}"
    )
