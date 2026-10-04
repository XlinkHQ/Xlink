from __future__ import annotations

from urllib.parse import urlencode

from app.subscription.formats.base import (
    FormatRenderError,
    require_fields,
    require_protocol,
    setting,
    validate_node,
)
from app.subscription.models import ProviderConfig

PROTOCOL = "mtproto"


def render(config: ProviderConfig) -> str:
    """Telegram proxy link. Fake-TLS secrets are "ee" + the user's 16-byte
    secret + the hex of the camouflage domain; Telegram reads the domain from
    the secret, so it must equal the server's TLS_DOMAIN."""
    require_protocol(config, PROTOCOL)
    require_fields(config, ("host", "port"))
    validate_node(config)
    secret = str(setting(config, "secret", "") or "").strip().lower()
    domain = str(setting(config, "tlsDomain", "") or "").strip().lower()
    if len(secret) != 32 or not domain:
        raise FormatRenderError(
            "MTProto requires a secret and tlsDomain.",
            code="subscription_missing_fields",
            details={
                "missing": [k for k, v in (("secret", secret), ("tlsDomain", domain)) if not v]
            },
        )
    full = "ee" + secret + domain.encode().hex()
    query = urlencode({"server": config.host, "port": config.port, "secret": full})
    return f"https://t.me/proxy?{query}"
