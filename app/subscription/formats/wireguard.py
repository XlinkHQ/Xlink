from __future__ import annotations

from app.subscription.formats.base import (
    FormatRenderError,
    require_fields,
    require_protocol,
    setting,
    validate_node,
)
from app.subscription.models import ProviderConfig

PROTOCOL = "wireguard"


def _ini_value(raw: object) -> str:
    return str(raw).replace("\r", " ").replace("\n", " ").strip()


def _int_setting(config: ProviderConfig, key: str, default: int, lo: int, hi: int) -> int:
    raw = setting(config, key)
    if raw in (None, ""):
        return default
    try:
        val = int(raw)
    except (TypeError, ValueError) as exc:
        raise FormatRenderError(
            f"WireGuard {key} must be an integer.",
            code="subscription_invalid_field",
            details={"field": key, "value": str(raw)},
        ) from exc
    if not (lo <= val <= hi):
        raise FormatRenderError(
            f"WireGuard {key} must be between {lo} and {hi}.",
            code="subscription_invalid_field",
            details={"field": key, "value": val},
        )
    return val


def _peer_block(config: ProviderConfig) -> str:
    public_key = _ini_value(setting(config, "peerPublicKey", setting(config, "publicKey", "")))
    if not public_key:
        raise FormatRenderError(
            "WireGuard requires a peer public key.",
            code="subscription_missing_fields",
            details={"missing": ["peerPublicKey"]},
        )
    allowed_ips = _ini_value(setting(config, "allowedIPs", "0.0.0.0/0, ::/0"))
    if "0.0.0.0/0" in allowed_ips and "::/0" not in allowed_ips:
        allowed_ips = f"{allowed_ips}, ::/0"
    endpoint_host = _ini_value(config.host)
    if ":" in endpoint_host and not endpoint_host.startswith("["):
        endpoint_host = f"[{endpoint_host}]"
    lines = [
        "[Peer]",
        f"PublicKey = {public_key}",
        f"Endpoint = {endpoint_host}:{config.port}",
        f"AllowedIPs = {allowed_ips}",
    ]
    preshared = _ini_value(setting(config, "presharedKey", ""))
    if preshared:
        lines.insert(2, f"PresharedKey = {preshared}")
    keepalive = _int_setting(config, "persistentKeepalive", 25, 1, 65535)
    lines.append(f"PersistentKeepalive = {keepalive}")
    return "\n".join(lines)


def _interface_block(config: ProviderConfig) -> str:
    private_key = _ini_value(setting(config, "privateKey", "") or "")
    if not private_key:
        raise FormatRenderError(
            "WireGuard requires a client private key.",
            code="subscription_missing_fields",
            details={"missing": ["privateKey"]},
        )
    address = _ini_value(setting(config, "address", "10.0.0.2/32"))
    lines = [
        "[Interface]",
        f"PrivateKey = {private_key}",
        f"Address = {address}",
    ]
    dns = _ini_value(setting(config, "dns", ""))
    if dns:
        lines.append(f"DNS = {dns}")
    mtu = _int_setting(config, "mtu", 1280, 1280, 65535)
    lines.append(f"MTU = {mtu}")
    return "\n".join(lines)


def render_one(config: ProviderConfig) -> str:
    require_protocol(config, PROTOCOL)
    require_fields(config, ("host", "port"))
    validate_node(config)
    return f"{_interface_block(config)}\n\n{_peer_block(config)}\n"


def render(configs: tuple[ProviderConfig, ...]) -> str:
    blocks = []
    for c in configs:
        if c.protocol != PROTOCOL:
            continue
        try:
            blocks.append(render_one(c))
        except FormatRenderError:
            continue
    return "\n".join(blocks)
