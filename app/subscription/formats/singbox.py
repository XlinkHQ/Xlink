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
        public_key = str(setting(config, "publicKey", setting(config, "pbk", "")) or "").strip()
        short_id = str(setting(config, "shortId", setting(config, "sid", "")) or "").strip()
        missing = [n for n, v in (("publicKey", public_key), ("shortId", short_id)) if not v]
        if missing:
            raise FormatRenderError(
                "REALITY requires a public key and short id.",
                code="subscription_missing_fields",
                details={"missing": missing},
            )
        # sing-box REALITY needs a uTLS fingerprint; default to chrome if unset.
        block.setdefault("utls", {"enabled": True, "fingerprint": fingerprint or "chrome"})
        block["reality"] = {
            "enabled": True,
            "public_key": public_key,
            "short_id": short_id,
        }
    alpn = str(setting(config, "alpn", "") or "").strip()
    if alpn:
        block["alpn"] = [a.strip() for a in alpn.split(",") if a.strip()]
    if setting(config, "allowInsecure"):
        block["insecure"] = True
    return block


def _transport_block(config: ProviderConfig) -> dict[str, Any] | None:
    network = str(setting(config, "network", "tcp"))
    host = str(setting(config, "host", "") or "").strip()
    if network == "ws":
        path = str(setting(config, "path", "/"))
        max_early_data = None
        if "?ed=" in path:
            path, ed = path.split("?ed=", 1)
            try:
                max_early_data = int(ed.split("/")[0])
            except ValueError:
                max_early_data = None
        t: dict[str, Any] = {"type": "ws", "path": path}
        if host:
            t["headers"] = {"Host": host}
        if max_early_data is not None:
            t["max_early_data"] = max_early_data
            t["early_data_header_name"] = "Sec-WebSocket-Protocol"
        return t
    if network == "grpc":
        g: dict[str, Any] = {"type": "grpc"}
        svc = str(setting(config, "serviceName", "") or "").strip()
        if svc:
            g["service_name"] = svc
        return g
    if network == "httpupgrade":
        path = str(setting(config, "path", "/"))
        if "?ed=" in path:
            path = path.split("?ed=", 1)[0]
        h: dict[str, Any] = {"type": "httpupgrade", "path": path}
        if host:
            h["host"] = host
        return h
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
        # The inner-ss password defaults to the per-user credential (an arbitrary
        # string), which is NOT a valid base64 32-byte 2022-blake3 PSK, and the
        # agent's shadowtls detour defaults to aes-128-gcm — so the client default
        # MUST match or the cipher negotiation fails on every out-of-box user.
        "method": str(setting(config, "method", "aes-128-gcm")),
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
            flow = str(setting(config, "flow", "") or "").strip()
            if flow:
                base["flow"] = flow
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
