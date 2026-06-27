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


def _default_ss_method(protocol: str) -> str:
    return "2022-blake3-aes-256-gcm" if protocol == "shadowsocks2022" else "aes-256-gcm"


def _shadowtls_outbounds(config: ProviderConfig, tag: str) -> list[dict[str, Any]]:
    st_tag = f"{tag}-shadowtls"
    st_tls: dict[str, Any] = {
        "enabled": True,
        "server_name": str(setting(config, "sni", setting(config, "host", ""))),
    }
    fingerprint = str(setting(config, "fingerprint", ""))
    if fingerprint:
        st_tls["utls"] = {"enabled": True, "fingerprint": fingerprint}
    shadowtls = {
        "type": "shadowtls",
        "tag": st_tag,
        "server": config.host,
        "server_port": config.port,
        "version": int(setting(config, "shadowtls_version", 3)),
        "password": str(setting(config, "shadowtls_password", config.resolved_password)),
        "tls": st_tls,
    }
    inner = {
        "type": "shadowsocks",
        "tag": tag,
        "method": str(setting(config, "method", "2022-blake3-aes-256-gcm")),
        "password": str(setting(config, "password", config.resolved_password)),
        "detour": st_tag,
    }
    return [shadowtls, inner]


def _outbounds(config: ProviderConfig) -> list[dict[str, Any]]:
    tag = f"{config.provider_name}-{config.inbound_tag}-{config.assignment_id}"
    protocol = config.protocol
    if protocol == "shadowtls":
        return _shadowtls_outbounds(config, tag)

    base: dict[str, Any] = {
        "tag": tag,
        "server": config.host,
        "server_port": config.port,
    }
    if protocol in ("vless", "vmess"):
        base["type"] = protocol
        base["uuid"] = config.resolved_uuid
        if protocol == "vless":
            base["flow"] = str(setting(config, "flow", ""))
        else:
            base["alter_id"] = int(setting(config, "alterId", 0))
    elif protocol == "trojan":
        base["type"] = "trojan"
        base["password"] = config.resolved_password
    elif protocol in ("shadowsocks", "shadowsocks2022"):
        base["type"] = "shadowsocks"
        base["method"] = str(setting(config, "method", _default_ss_method(protocol)))
        base["password"] = str(setting(config, "password", config.resolved_password))
    elif protocol == "hysteria2":
        base["type"] = "hysteria2"
        base["password"] = config.resolved_password
    elif protocol == "tuic":
        base["type"] = "tuic"
        base["uuid"] = config.resolved_uuid
        base["password"] = str(setting(config, "password", "") or config.resolved_password)
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
    return [base]


def render(configs: tuple[ProviderConfig, ...]) -> str:
    outbounds: list[dict[str, Any]] = []
    for config in configs:
        try:
            validate_node(config)
            outbounds.extend(_outbounds(config))
        except FormatRenderError:
            continue
    document = {"outbounds": outbounds}
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)
