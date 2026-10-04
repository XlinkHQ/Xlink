"""Operator passthrough for client-side outbounds.

Mirrors the agent's `rawInbound`: a profile may carry `rawClientOutbound`, a
dict in the target client's own JSON, deep-merged onto the generated outbound.
It lets an operator use a client feature the renderers do not model yet (a new
transport knob, mux, a uTLS tweak) without a panel release.

Identity is protected at the top level and destination/credential keys at
every depth, so an override cannot hand a user someone else's server or
password.
"""

from __future__ import annotations

from typing import Any

from app.subscription.models import ProviderConfig

# Identity: forbidden at the top level only.
_PROTECTED = frozenset({"tag", "type", "protocol", "server", "server_port"})
# Destination and credentials: forbidden at ANY depth. An xray-json outbound
# keeps its server under settings.vnext / settings.servers, so a top-level-only
# filter let an override silently point a user's client at another server.
_DEEP_PROTECTED = frozenset(
    {"uuid", "password", "users", "vnext", "servers", "address", "port", "id"}
)


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        # casefold: the clients that consume this JSON are Go, whose
        # encoding/json matches field names case-insensitively.
        return {
            k: _strip(v) for k, v in value.items() if str(k).casefold() not in _DEEP_PROTECTED
        }
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def apply(outbound: dict[str, Any], config: ProviderConfig) -> dict[str, Any]:
    raw = config.settings.get("rawClientOutbound")
    if not isinstance(raw, dict) or not raw:
        return outbound
    top = {k: v for k, v in raw.items() if str(k).casefold() not in _PROTECTED}
    return _deep_merge(outbound, _strip(top))
