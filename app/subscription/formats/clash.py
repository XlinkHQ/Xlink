from __future__ import annotations

from typing import Any

import yaml

from app.subscription.formats.base import (
    FormatRenderError,
    label,
    setting,
    setting_int,
    validate_node,
)
from app.subscription.formats.capabilities import supported_protocols
from app.subscription.models import ProviderConfig
from app.subscription.schemas import SubscriptionFormat

CLASH_PROTOCOLS = supported_protocols(SubscriptionFormat.CLASH_YAML)
MIHOMO_PROTOCOLS = supported_protocols(SubscriptionFormat.MIHOMO_YAML)


def _proxy_name(config: ProviderConfig) -> str:

    remark = label(config, encoded=False).strip()
    base = f"{config.provider_name}-{config.inbound_tag}-{config.assignment_id}"
    if remark and remark != config.inbound_tag and remark != config.provider_name:
        return f"{remark} ({str(config.assignment_id)[:8]})"
    return base


def _tls_fields(config: ProviderConfig, proxy: dict[str, Any]) -> None:
    security = str(setting(config, "security", "none"))
    if security in ("tls", "reality"):
        proxy["tls"] = True
        servername = str(setting(config, "sni", setting(config, "host", "")))
        if servername:
            proxy["servername"] = servername
        fingerprint = str(setting(config, "fingerprint", ""))
        if fingerprint:
            proxy["client-fingerprint"] = fingerprint
        if security == "reality":
            proxy["reality-opts"] = {
                "public-key": str(setting(config, "publicKey", setting(config, "pbk", ""))),
                "short-id": str(setting(config, "shortId", setting(config, "sid", ""))),
            }
        alpn = setting(config, "alpn")
        if alpn:
            parsed = (
                [str(a).strip() for a in alpn if str(a).strip()]
                if isinstance(alpn, (list, tuple))
                else [a.strip() for a in str(alpn).split(",") if a.strip()]
            )
            if parsed:
                proxy["alpn"] = parsed
        if setting(config, "allowInsecure"):
            proxy["skip-cert-verify"] = True


def _network_fields(config: ProviderConfig, proxy: dict[str, Any]) -> None:
    network = str(setting(config, "network", "tcp"))
    if network == "ws":
        proxy["network"] = "ws"
        proxy["ws-opts"] = {"path": str(setting(config, "path", "/"))}
        host = str(setting(config, "host", ""))
        if host:
            proxy["ws-opts"]["headers"] = {"Host": host}
    elif network == "grpc":
        proxy["network"] = "grpc"
        proxy["grpc-opts"] = {"grpc-service-name": str(setting(config, "serviceName", ""))}
    elif network == "httpupgrade":
        proxy["network"] = "httpupgrade"
        proxy["httpupgrade-opts"] = {"path": str(setting(config, "path", "/"))}
        host = str(setting(config, "host", ""))
        if host:
            proxy["httpupgrade-opts"]["host"] = host


def build_proxy(config: ProviderConfig, *, allowed: frozenset[str]) -> dict[str, Any]:
    validate_node(config)
    protocol = config.protocol
    if protocol not in allowed:
        raise FormatRenderError(
            f"Clash family does not support protocol '{protocol}'.",
            code="subscription_protocol_unsupported",
            details={"protocol": protocol},
        )
    proxy: dict[str, Any] = {
        "name": _proxy_name(config),
        "server": config.host,
        "port": config.port,
    }
    if protocol == "vless":
        proxy["type"] = "vless"
        proxy["uuid"] = config.resolved_uuid
        flow = str(setting(config, "flow", ""))
        if flow:
            proxy["flow"] = flow
        _tls_fields(config, proxy)
        _network_fields(config, proxy)
    elif protocol == "vmess":
        proxy["type"] = "vmess"
        proxy["uuid"] = config.resolved_uuid
        proxy["alterId"] = setting_int(config, "alterId", 0)
        proxy["cipher"] = str(setting(config, "cipher", "auto"))
        _tls_fields(config, proxy)
        _network_fields(config, proxy)
    elif protocol == "trojan":
        proxy["type"] = "trojan"
        proxy["password"] = config.resolved_password
        _tls_fields(config, proxy)
        _network_fields(config, proxy)
    elif protocol in ("shadowsocks", "shadowsocks2022"):
        proxy["type"] = "ss"
        default_method = (
            "2022-blake3-aes-256-gcm" if protocol == "shadowsocks2022" else "aes-256-gcm"
        )
        proxy["cipher"] = str(setting(config, "method", default_method))
        proxy["password"] = config.resolved_password
    elif protocol == "shadowtls":
        proxy["type"] = "ss"
        proxy["cipher"] = str(setting(config, "method", "aes-128-gcm"))
        proxy["password"] = str(setting(config, "password", config.resolved_password))
        proxy["plugin"] = "shadow-tls"
        proxy["plugin-opts"] = {
            "host": str(setting(config, "sni", setting(config, "host", ""))),
            "password": str(setting(config, "shadowtls_password", config.resolved_password)),
            "version": setting_int(config, "shadowtls_version", 3),
        }
    elif protocol == "hysteria2":
        proxy["type"] = "hysteria2"
        proxy["password"] = config.resolved_password
        proxy["sni"] = str(setting(config, "sni", setting(config, "host", "")))
    elif protocol == "tuic":
        proxy["type"] = "tuic"
        proxy["uuid"] = config.resolved_uuid
        proxy["password"] = str(setting(config, "password", "") or config.resolved_password)
        proxy["sni"] = str(setting(config, "sni", setting(config, "host", "")))
    elif protocol in ("socks", "http"):
        proxy["type"] = "socks5" if protocol == "socks" else "http"
        if setting(config, "username"):
            proxy["username"] = str(setting(config, "username"))
            proxy["password"] = str(setting(config, "password", ""))
    if protocol in ("vless", "vmess", "trojan", "shadowsocks", "shadowsocks2022", "shadowtls"):
        proxy["udp"] = True
    return proxy


def build_clash_document(configs: tuple[ProviderConfig, ...], *, allowed: frozenset[str]) -> str:
    proxies = []
    for config in configs:
        try:
            proxies.append(build_proxy(config, allowed=allowed))
        except FormatRenderError:
            continue
    if configs and not proxies:
        raise FormatRenderError("No CLASH-compatible proxies in feed.")
    names = [proxy["name"] for proxy in proxies]
    document = {
        "proxies": proxies,
        "proxy-groups": [
            {"name": "PROXY", "type": "select", "proxies": names or ["DIRECT"]},
        ],
        "rules": ["MATCH,PROXY"],
    }
    return yaml.safe_dump(document, sort_keys=True, allow_unicode=True, default_flow_style=False)


def render(configs: tuple[ProviderConfig, ...]) -> str:
    return build_clash_document(configs, allowed=CLASH_PROTOCOLS)
