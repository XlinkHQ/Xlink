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
    if network in ("ws", "httpupgrade", "splithttp"):
        params["path"] = str(setting(config, "path", "/"))
        params["host"] = str(setting(config, "host", ""))
    elif network == "xhttp":
        params["path"] = str(setting(config, "path", "/"))
        params["host"] = str(setting(config, "host", ""))
        params["mode"] = str(setting(config, "mode", "auto"))
    elif network == "grpc":
        params["serviceName"] = str(setting(config, "serviceName", ""))
    elif network == "kcp":
        params["headerType"] = str(setting(config, "headerType", "none"))
    elif network == "tcp":
        params["headerType"] = str(setting(config, "headerType", ""))
    if security == "tls":
        params["sni"] = str(setting(config, "sni", setting(config, "host", "")))
        params["fp"] = str(setting(config, "fingerprint", "") or "chrome")
        params["alpn"] = str(setting(config, "alpn", ""))
    elif security == "reality":
        params["sni"] = str(setting(config, "sni", ""))
        params["fp"] = str(setting(config, "fingerprint", "") or "chrome")
        params["pbk"] = str(setting(config, "publicKey", setting(config, "pbk", "")))
        params["sid"] = str(setting(config, "shortId", setting(config, "sid", "")))
        params["alpn"] = str(setting(config, "alpn", ""))
        params["spx"] = str(setting(config, "spiderX", ""))
    if security in ("tls", "reality") and setting(config, "allowInsecure"):
        params["allowInsecure"] = "1"
    return params


def render(config: ProviderConfig) -> str:
    require_protocol(config, PROTOCOL)
    require_fields(config, ("client_id", "host", "port"))
    validate_node(config)
    params = transport_params(config)
    params["flow"] = str(setting(config, "flow", ""))
    return (
        f"vless://{quote(config.resolved_uuid)}@{config.host}:{config.port}"
        f"?{query(params)}#{label(config)}"
    )
