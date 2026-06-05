from __future__ import annotations

from urllib.parse import quote

from app.subscription.formats.base import (
    label,
    require_fields,
    require_protocol,
    setting,
    validate_node,
)
from app.subscription.models import ProviderConfig

PROTOCOL = "naive"


def render(config: ProviderConfig) -> str:
    require_protocol(config, PROTOCOL)
    require_fields(config, ("host", "port", "username", "password"))
    validate_node(config)
    username = quote(str(setting(config, "username")))
    password = quote(str(setting(config, "password")))
    padding = setting(config, "padding")
    extra = "?padding=true" if padding else ""
    return f"naive+https://{username}:{password}@{config.host}:{config.port}{extra}#{label(config)}"
