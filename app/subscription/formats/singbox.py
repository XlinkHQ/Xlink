from __future__ import annotations

import json
from typing import Any

from app.subscription.formats.base import FormatRenderError, setting, validate_node
from app.subscription.models import ProviderConfig


def _tls_block(config: ProviderConfig) -> dict[str, Any] | None:
    security = str(setting(config, "security", "none"))
    if security not in ("tls", "reality"):
        return None
    block: dict[str, Any] = {
        "enabled": True,
        "server_name": str(setting(config, "sni", setting(config, "host", ""))),
    }
    fingerprint = str(setting(config, "fingerprint", ""))
    if fingerprint:
        block["utls"] = {"enabled": True, "fingerprint": fingerprint}
    if security == "reality":
        block["reality"] = {
            "enabled": True,
            "public_key": str(setting(config, "publicKey", setting(config, "pbk", ""))),
            "short_id": str(setting(config, "shortId", setting(config, "sid", ""))),
        }
    return block


def _transport_block(config: ProviderConfig) -> dict[str, Any] | None:
    network = str(setting(config, "network", "tcp"))
    if network == "ws":
        return {"type": "ws", "path": str(setting(config, "path", "/"))}
    if network == "grpc":
        return {"type": "grpc", "service_name": str(setting(config, "serviceName", ""))}
    if network == "httpupgrade":
        return {"type": "httpupgrade", "path": str(setting(config, "path", "/"))}
    return None


def _outbound(config: ProviderConfig) -> dict[str, Any]:
    tag = f"{config.provider_name}-{config.inbound_tag}-{config.assignment_id}"
    base: dict[str, Any] = {
        "tag": tag,
        "server": config.host,
        "server_port": config.port,
    }
    protocol = config.protocol
    if protocol in ("vless", "vmess"):
        base["type"] = protocol
        base["uuid"] = config.client_id
        if protocol == "vless":
            base["flow"] = str(setting(config, "flow", ""))
        else:
            base["alter_id"] = int(setting(config, "alterId", 0))
    elif protocol == "trojan":
        base["type"] = "trojan"
        base["password"] = config.client_id
    elif protocol == "shadowsocks":
        base["type"] = "shadowsocks"
        base["method"] = str(setting(config, "method"))
        base["password"] = str(setting(config, "password"))
    elif protocol == "hysteria2":
        base["type"] = "hysteria2"
        base["password"] = config.client_id
    elif protocol == "tuic":
        base["type"] = "tuic"
        base["uuid"] = config.client_id
        base["password"] = str(setting(config, "password"))
    elif protocol in ("socks", "http"):
        base["type"] = protocol
        if setting(config, "username"):
            base["username"] = str(setting(config, "username"))
            base["password"] = str(setting(config, "password", ""))
    else:
        raise FormatRenderError(
            f"sing-box does not support protocol '{protocol}'.",
            code="subscription_protocol_unsupported",
            details={"protocol": protocol},
        )
    tls = _tls_block(config)
    if tls is not None:
        base["tls"] = tls
    transport = _transport_block(config)
    if transport is not None:
        base["transport"] = transport
    return base


def render(configs: tuple[ProviderConfig, ...]) -> str:
    outbounds = []
    for config in configs:
        validate_node(config)
        outbounds.append(_outbound(config))
    document = {"outbounds": outbounds}
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)
