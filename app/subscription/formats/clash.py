from __future__ import annotations

from typing import Any

import yaml

from app.subscription.formats.base import FormatRenderError, setting, validate_node
from app.subscription.models import ProviderConfig

CLASH_PROTOCOLS = frozenset({"vless", "vmess", "trojan", "shadowsocks"})
MIHOMO_PROTOCOLS = CLASH_PROTOCOLS | frozenset({"hysteria2", "tuic", "socks", "http"})


def _proxy_name(config: ProviderConfig) -> str:
    return f"{config.provider_name}-{config.inbound_tag}-{config.assignment_id}"


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
        proxy["uuid"] = config.client_id
        flow = str(setting(config, "flow", ""))
        if flow:
            proxy["flow"] = flow
        _tls_fields(config, proxy)
        _network_fields(config, proxy)
    elif protocol == "vmess":
        proxy["type"] = "vmess"
        proxy["uuid"] = config.client_id
        proxy["alterId"] = int(setting(config, "alterId", 0))
        proxy["cipher"] = str(setting(config, "cipher", "auto"))
        _tls_fields(config, proxy)
        _network_fields(config, proxy)
    elif protocol == "trojan":
        proxy["type"] = "trojan"
        proxy["password"] = config.client_id
        _tls_fields(config, proxy)
        _network_fields(config, proxy)
    elif protocol == "shadowsocks":
        proxy["type"] = "ss"
        proxy["cipher"] = str(setting(config, "method"))
        proxy["password"] = str(setting(config, "password"))
    elif protocol == "hysteria2":
        proxy["type"] = "hysteria2"
        proxy["password"] = config.client_id
        proxy["sni"] = str(setting(config, "sni", setting(config, "host", "")))
    elif protocol == "tuic":
        proxy["type"] = "tuic"
        proxy["uuid"] = config.client_id
        proxy["password"] = str(setting(config, "password"))
        proxy["sni"] = str(setting(config, "sni", setting(config, "host", "")))
    elif protocol in ("socks", "http"):
        proxy["type"] = "socks5" if protocol == "socks" else "http"
        if setting(config, "username"):
            proxy["username"] = str(setting(config, "username"))
            proxy["password"] = str(setting(config, "password", ""))
    return proxy


def build_clash_document(configs: tuple[ProviderConfig, ...], *, allowed: frozenset[str]) -> str:
    proxies = [build_proxy(config, allowed=allowed) for config in configs]
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
