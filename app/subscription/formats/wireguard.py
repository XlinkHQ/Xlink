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


def _peer_block(config: ProviderConfig) -> str:
    public_key = str(setting(config, "peerPublicKey", setting(config, "publicKey", "")))
    if not public_key:
        raise FormatRenderError(
            "WireGuard requires a peer public key.",
            code="subscription_missing_fields",
            details={"missing": ["peerPublicKey"]},
        )
    allowed_ips = str(setting(config, "allowedIPs", "0.0.0.0/0, ::/0"))
    lines = [
        "[Peer]",
        f"PublicKey = {public_key}",
        f"Endpoint = {config.host}:{config.port}",
        f"AllowedIPs = {allowed_ips}",
    ]
    preshared = str(setting(config, "presharedKey", ""))
    if preshared:
        lines.insert(2, f"PresharedKey = {preshared}")
    keepalive = setting(config, "persistentKeepalive") or 25
    lines.append(f"PersistentKeepalive = {int(keepalive)}")
    return "\n".join(lines)


def _interface_block(config: ProviderConfig) -> str:
    private_key = str(setting(config, "privateKey", config.client_id))
    address = str(setting(config, "address", "10.0.0.2/32"))
    lines = [
        "[Interface]",
        f"PrivateKey = {private_key}",
        f"Address = {address}",
    ]
    dns = str(setting(config, "dns", ""))
    if dns:
        lines.append(f"DNS = {dns}")
    mtu = setting(config, "mtu")
    if mtu:
        lines.append(f"MTU = {int(mtu)}")
    return "\n".join(lines)


def render_one(config: ProviderConfig) -> str:
    require_protocol(config, PROTOCOL)
    require_fields(config, ("host", "port"))
    validate_node(config)
    return f"{_interface_block(config)}\n\n{_peer_block(config)}\n"


def render(configs: tuple[ProviderConfig, ...]) -> str:
    blocks = [render_one(c) for c in configs if c.protocol == PROTOCOL]
    return "\n".join(blocks)
