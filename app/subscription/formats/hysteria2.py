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

PROTOCOL = "hysteria2"


def render(config: ProviderConfig) -> str:
    require_protocol(config, PROTOCOL)
    require_fields(config, ("client_id", "host", "port"))
    validate_node(config)
    insecure = "1" if setting(config, "allowInsecure") else "0"
    sni = str(setting(config, "sni", "") or setting(config, "host", "") or config.host)
    params = query(
        {
            "sni": sni,
            "insecure": insecure,
            "obfs": setting(config, "obfs", ""),
            "obfs-password": setting(config, "obfsPassword", ""),
        }
    )
    auth = quote(config.resolved_password)
    suffix = f"?{params}" if params else ""
    return f"hysteria2://{auth}@{config.host}:{config.port}{suffix}#{label(config)}"
