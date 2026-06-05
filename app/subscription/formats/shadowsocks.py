from __future__ import annotations

import base64

from app.subscription.formats.base import (
    label,
    require_fields,
    require_protocol,
    setting,
    validate_node,
)
from app.subscription.models import ProviderConfig

PROTOCOL = "shadowsocks"


def render(config: ProviderConfig) -> str:
    require_protocol(config, PROTOCOL)
    require_fields(config, ("host", "port", "method", "password"))
    validate_node(config)
    method = str(setting(config, "method"))
    password = str(setting(config, "password"))
    userinfo = base64.urlsafe_b64encode(f"{method}:{password}".encode()).decode("ascii").rstrip("=")
    return f"ss://{userinfo}@{config.host}:{config.port}#{label(config)}"
