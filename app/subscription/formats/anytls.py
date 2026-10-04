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

PROTOCOL = "anytls"


def render(config: ProviderConfig) -> str:
    """`anytls://<password>@host:port?sni=...#label` (anytls-go / Mihomo form).

    AnyTLS hides the proxy inside a padded TLS session to defeat traffic-shape
    fingerprinting; it is TLS-only, so `sni` is always emitted.
    """
    require_protocol(config, PROTOCOL)
    require_fields(config, ("client_id", "host", "port"))
    validate_node(config)

    password = quote(str(setting(config, "password", "") or config.resolved_password))
    params = query(
        {
            "sni": setting(config, "sni", setting(config, "host", "")) or config.host,
            "insecure": "1" if setting(config, "allowInsecure") else "",
            "fp": setting(config, "fingerprint", ""),
        }
    )
    suffix = f"?{params}" if params else ""
    return f"anytls://{password}@{config.host}:{config.port}{suffix}#{label(config)}"
