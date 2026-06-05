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

PROTOCOL = "vless"


def transport_params(config: ProviderConfig) -> dict[str, str]:
    network = str(setting(config, "network", "tcp"))
    security = str(setting(config, "security", "none"))
    params: dict[str, str] = {"type": network, "security": security}
    if network in ("ws", "httpupgrade"):
        params["path"] = str(setting(config, "path", "/"))
        params["host"] = str(setting(config, "host", ""))
    elif network == "grpc":
        params["serviceName"] = str(setting(config, "serviceName", ""))
    else:
        params["headerType"] = str(setting(config, "headerType", ""))
    if security == "tls":
        params["sni"] = str(setting(config, "sni", setting(config, "host", "")))
        params["fp"] = str(setting(config, "fingerprint", ""))
        params["alpn"] = str(setting(config, "alpn", ""))
    elif security == "reality":
        params["sni"] = str(setting(config, "sni", ""))
        params["fp"] = str(setting(config, "fingerprint", ""))
        params["pbk"] = str(setting(config, "publicKey", setting(config, "pbk", "")))
        params["sid"] = str(setting(config, "shortId", setting(config, "sid", "")))
    return params


def render(config: ProviderConfig) -> str:
    require_protocol(config, PROTOCOL)
    require_fields(config, ("client_id", "host", "port"))
    validate_node(config)
    params = transport_params(config)
    params["flow"] = str(setting(config, "flow", ""))
    return (
        f"vless://{quote(config.client_id)}@{config.host}:{config.port}"
        f"?{query(params)}#{label(config)}"
    )
