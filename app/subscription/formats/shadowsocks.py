from __future__ import annotations

import base64

from app.subscription.formats.base import (
    FormatRenderError,
    label,
    require_fields,
    setting,
    validate_node,
)
from app.subscription.models import ProviderConfig

PROTOCOL = "shadowsocks"

PROTOCOLS = ("shadowsocks", "shadowsocks2022")


def render(config: ProviderConfig) -> str:
    if config.protocol not in PROTOCOLS:
        raise FormatRenderError(
            f"Expected a shadowsocks config, got '{config.protocol}'.",
            code="subscription_protocol_unsupported",
            details={"protocol": config.protocol},
        )
    require_fields(config, ("host", "port"))
    validate_node(config)

    default_method = (
        "2022-blake3-aes-256-gcm" if config.protocol == "shadowsocks2022" else "aes-256-gcm"
    )
    method = str(setting(config, "method", default_method))
    password = config.resolved_password
    userinfo = base64.urlsafe_b64encode(f"{method}:{password}".encode()).decode("ascii").rstrip("=")
    return f"ss://{userinfo}@{config.host}:{config.port}#{label(config)}"
