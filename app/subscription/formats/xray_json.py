from __future__ import annotations

import hashlib
import json

from app.subscription.formats import raw_override
from app.subscription.formats.base import (
    FormatRenderError,
    label,
    normalize_alpn,
    setting,
    setting_int,
)
from app.subscription.formats.capabilities import supported_protocols
from app.subscription.models import ProviderConfig
from app.subscription.schemas import SubscriptionFormat

PROTOCOL = "xray_json"

_UA_POOL = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36",
)


def _truthy(value: object) -> bool:
    return str(value).lower() in ("1", "true", "yes", "on")


def _random_ua(config: ProviderConfig) -> str:

    digest = hashlib.sha256(str(config.client_id).encode()).hexdigest()
    return _UA_POOL[int(digest, 16) % len(_UA_POOL)]


def _stream(config: ProviderConfig) -> dict:
    network = str(setting(config, "network", "tcp"))
    security = str(setting(config, "security", "none"))
    stream: dict = {"network": network, "security": security}
    host = str(setting(config, "host", ""))
    path = str(setting(config, "path", "/"))

    headers: dict[str, str] = {}
    if host:
        headers["Host"] = host
    if _truthy(setting(config, "randomUserAgent", "")):
        headers["User-Agent"] = _random_ua(config)

    if network == "ws":
        ws: dict = {"path": path}
        if headers:
            ws["headers"] = headers
        stream["wsSettings"] = ws
    elif network == "httpupgrade":
        stream["httpupgradeSettings"] = {"path": path, **({"host": host} if host else {})}
    elif network == "grpc":
        stream["grpcSettings"] = {"serviceName": str(setting(config, "serviceName", ""))}
    elif network in ("xhttp", "splithttp"):
        stream[f"{network}Settings"] = {"path": path, **({"host": host} if host else {})}

    if security == "tls":
        tls: dict = {"serverName": str(setting(config, "sni", host))}
        alpn = normalize_alpn(config)
        if alpn:
            tls["alpn"] = alpn
        if setting(config, "fingerprint", ""):
            tls["fingerprint"] = str(setting(config, "fingerprint", ""))

        stream["tlsSettings"] = tls
    elif security == "reality":
        stream["realitySettings"] = {
            "serverName": str(setting(config, "sni", "")),
            "fingerprint": str(setting(config, "fingerprint", "chrome")),
            "publicKey": str(setting(config, "publicKey", setting(config, "pbk", ""))),
            "shortId": str(setting(config, "shortId", setting(config, "sid", ""))),
            "spiderX": str(setting(config, "spiderX", "")),
        }
    return stream


def _proxy_outbound(config: ProviderConfig) -> dict:
    proto = config.protocol
    if proto == "vless":
        user = {"id": config.resolved_uuid, "encryption": "none"}
        if setting(config, "flow", ""):
            user["flow"] = str(setting(config, "flow", ""))
        settings = {"vnext": [{"address": config.host, "port": config.port, "users": [user]}]}
    elif proto == "vmess":
        user = {
            "id": config.resolved_uuid,
            "alterId": setting_int(config, "alterId", 0),
            "security": str(setting(config, "cipher", "auto")),
        }
        settings = {"vnext": [{"address": config.host, "port": config.port, "users": [user]}]}
    elif proto == "trojan":
        settings = {
            "servers": [
                {"address": config.host, "port": config.port, "password": config.resolved_password}
            ]
        }
    else:
        raise FormatRenderError(
            f"xray_json does not support protocol '{proto}'.",
            code="subscription_format_incompatible",
            details={"protocol": proto},
        )

    out: dict = {
        "tag": "proxy",
        "protocol": proto,
        "settings": settings,
        "streamSettings": _stream(config),
    }
    if _truthy(setting(config, "mux", "")):
        out["mux"] = {"enabled": True, "concurrency": 8}
    return raw_override.apply(out, config)


def _fragment_outbound(config: ProviderConfig) -> dict | None:
    fragment = str(setting(config, "fragment", "")).strip()
    noise = str(setting(config, "noise", "")).strip()
    if not fragment and not noise:
        return None
    settings: dict = {"domainStrategy": "AsIs"}
    if fragment:
        length, _, rest = fragment.partition(",")
        interval, _, packets = rest.partition(",")
        settings["fragment"] = {
            "length": length.strip() or "100-200",
            "interval": interval.strip() or "10-20",
            "packets": packets.strip() or "tlshello",
        }
    if noise:
        head, _, delay = noise.partition(",")
        ntype, _, packet = head.partition(":")
        settings["noises"] = [
            {
                "type": ntype.strip() or "rand",
                "packet": packet.strip() or head.strip(),
                "delay": delay.strip() or "10-20",
            }
        ]
    return {"tag": "fragment", "protocol": "freedom", "settings": settings}


def render_one(config: ProviderConfig) -> dict:
    proxy = _proxy_outbound(config)
    outbounds = [proxy]
    fragment = _fragment_outbound(config)
    if fragment is not None:
        proxy.setdefault("streamSettings", {}).setdefault("sockopt", {})["dialerProxy"] = "fragment"
        outbounds.append(fragment)
    outbounds.append({"tag": "direct", "protocol": "freedom", "settings": {}})
    outbounds.append({"tag": "block", "protocol": "blackhole", "settings": {}})
    return {
        "remarks": label(config, encoded=False),
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks",
                "port": 10808,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {"udp": True, "auth": "noauth"},
            },
            {
                "tag": "http",
                "port": 10809,
                "listen": "127.0.0.1",
                "protocol": "http",
                "settings": {},
            },
        ],
        "outbounds": outbounds,
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {"type": "field", "outboundTag": "direct", "domain": ["geosite:private"]},
            ],
        },
    }


def render(configs: tuple[ProviderConfig, ...]) -> str:
    allowed = supported_protocols(SubscriptionFormat.XRAY_JSON)
    out = []
    for c in configs:
        if c.protocol not in allowed:
            continue
        try:
            out.append(render_one(c))
        except FormatRenderError:
            continue
    return json.dumps(out, indent=2, ensure_ascii=False)
