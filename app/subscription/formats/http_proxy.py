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

PROTOCOL = "http"


def render(config: ProviderConfig) -> str:
    require_protocol(config, PROTOCOL)
    require_fields(config, ("host", "port"))
    validate_node(config)
    username = str(setting(config, "username", ""))
    password = str(setting(config, "password", ""))
    scheme = "https" if setting(config, "tls") else "http"
    userinfo = f"{quote(username)}:{quote(password)}@" if username or password else ""
    return f"{scheme}://{userinfo}{config.host}:{config.port}#{label(config)}"
