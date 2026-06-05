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

PROTOCOL = "socks"


def render(config: ProviderConfig) -> str:
    require_protocol(config, PROTOCOL)
    require_fields(config, ("host", "port"))
    validate_node(config)
    username = str(setting(config, "username", ""))
    password = str(setting(config, "password", ""))
    if username or password:
        userinfo = base64.urlsafe_b64encode(f"{username}:{password}".encode()).decode("ascii")
        userinfo = userinfo.rstrip("=") + "@"
    else:
        userinfo = ""
    return f"socks://{userinfo}{config.host}:{config.port}#{label(config)}"
