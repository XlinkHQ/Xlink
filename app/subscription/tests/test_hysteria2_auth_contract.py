"""The hysteria2 server/client auth shapes must agree.

The node agent builds `auth: {type: userpass, userpass: {<assignment_id>: <cid>}}`
and hysteria's traffic API reports usage back keyed on that same username, so
the username is load-bearing for accounting and cannot be dropped.

The client renderers used to send only a bare password, with no username at
all, so authentication failed for every hysteria2 user. These tests pin both
halves of the contract.
"""

from __future__ import annotations

import uuid
from urllib.parse import unquote, urlparse

from app.providers.base.models import ProviderKind
from app.subscription.formats import hysteria2 as uri_renderer
from app.subscription.models import ProviderConfig


def _config(**over) -> ProviderConfig:
    base: dict = {
        "assignment_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "provider_kind": ProviderKind.HYSTERIA,
        "provider_name": "hysteria",
        "protocol": "hysteria2",
        "client_id": "client-secret-123",
        "email": None,
        "inbound_tag": "hy2-in",
        "host": "vpn.example.com",
        "port": 443,
        "expires_at": None,
        "traffic_limit_bytes": None,
        "settings": {},
    }
    base.update(over)
    return ProviderConfig(**base)


def test_uri_carries_assignment_id_as_the_username() -> None:
    cfg = _config()
    uri = uri_renderer.render(cfg)
    userinfo = urlparse(uri).netloc.split("@")[0]
    assert ":" in userinfo, f"no username component in {userinfo!r}"
    user, password = userinfo.split(":", 1)
    assert unquote(user) == str(cfg.assignment_id)
    assert unquote(password) == cfg.resolved_password


def test_uri_username_matches_what_the_server_keys_on() -> None:
    """The agent writes `userpass[str(assignment_id)] = client_id`."""
    cfg = _config()
    server_map = {str(cfg.assignment_id): cfg.resolved_password}

    userinfo = urlparse(uri_renderer.render(cfg)).netloc.split("@")[0]
    user, password = (unquote(p) for p in userinfo.split(":", 1))

    assert server_map.get(user) == password, "client credentials do not open the server map"


def test_explicit_password_setting_is_used_as_the_password_half() -> None:
    cfg = _config(settings={"password": "operator-chosen"})
    userinfo = urlparse(uri_renderer.render(cfg)).netloc.split("@")[0]
    user, password = (unquote(p) for p in userinfo.split(":", 1))
    assert user == str(cfg.assignment_id)
    assert password == "operator-chosen"
