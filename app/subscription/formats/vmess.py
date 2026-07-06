from __future__ import annotations

import base64
import json

from app.subscription.formats.base import (
    label,
    require_fields,
    require_protocol,
    setting,
    validate_node,
)
from app.subscription.models import ProviderConfig

PROTOCOL = "vmess"


def _vmess_object(config: ProviderConfig) -> dict[str, str]:
    network = str(setting(config, "network", "tcp"))
    security = str(setting(config, "security", "none"))
    service_name = str(setting(config, "serviceName", "")) if network == "grpc" else ""
    obj = {
        "v": "2",
        "ps": label(config, encoded=False),
        "add": config.host,
        "port": str(config.port),
        "id": config.resolved_uuid,
        "aid": str(setting(config, "alterId", 0)),
        "scy": str(setting(config, "cipher", "auto")),
        "net": network,
        "type": str(setting(config, "headerType", "none")),
        "host": str(setting(config, "host", "")),
        "path": str(setting(config, "path", service_name)),
        "tls": "tls" if security in ("tls", "reality") else "",
        "sni": str(setting(config, "sni", "")),
        "fp": str(setting(config, "fingerprint", "")),
    }
    if security == "reality":
        obj["pbk"] = str(setting(config, "publicKey", setting(config, "pbk", "")))
        obj["sid"] = str(setting(config, "shortId", setting(config, "sid", "")))
        if not obj["fp"]:
            obj["fp"] = str(setting(config, "fingerprint", "chrome"))
    return obj


def render(config: ProviderConfig) -> str:
    require_protocol(config, PROTOCOL)
    require_fields(config, ("client_id", "host", "port"))
    validate_node(config)
    raw = json.dumps(_vmess_object(config), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"vmess://{base64.b64encode(raw).decode('ascii')}"
