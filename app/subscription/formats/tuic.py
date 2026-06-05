from __future__ import annotations

from urllib.parse import quote

from app.subscription.formats.base import (
    label,
    query,
    require_fields,
    require_protocol,
    setting,
    validate_node,
)
from app.subscription.models import ProviderConfig

PROTOCOL = "tuic"


def render(config: ProviderConfig) -> str:
    require_protocol(config, PROTOCOL)
    require_fields(config, ("client_id", "host", "port", "password"))
    validate_node(config)
    password = quote(str(setting(config, "password")))
    params = query(
        {
            "sni": setting(config, "sni", setting(config, "host", "")),
            "alpn": setting(config, "alpn", "h3"),
            "congestion_control": setting(config, "congestionControl", "bbr"),
            "udp_relay_mode": setting(config, "udpRelayMode", "native"),
            "allow_insecure": "1" if setting(config, "allowInsecure") else "",
        }
    )
    suffix = f"?{params}" if params else ""
    return f"tuic://{quote(config.client_id)}:{password}@{config.host}:{config.port}{suffix}#{label(config)}"
