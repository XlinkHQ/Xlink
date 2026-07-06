from __future__ import annotations

import hashlib
import hmac
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode

from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.subscription.schemas import FeedScope

_TOKEN_VERSION = b"\x02"
_SCOPE_MAP: dict[FeedScope, int] = {
    FeedScope.USER: 0,
    FeedScope.PROFILE: 1,
    FeedScope.ASSIGNMENT: 2,
}
_SCOPE_REVERSE: dict[int, FeedScope] = {v: k for k, v in _SCOPE_MAP.items()}


def create_subscription_token(
    user_id: uuid.UUID,
    scope: FeedScope,
    settings: Settings,
    revision: int = 0,
) -> str:
    payload = (
        _TOKEN_VERSION
        + _SCOPE_MAP[scope].to_bytes(1, "big")
        + user_id.bytes
        + max(0, revision).to_bytes(4, "big")
    )
    signature = _sign(payload, settings)
    raw = payload + signature
    return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def verify_subscription_token(
    token: str,
    settings: Settings,
) -> tuple[uuid.UUID, FeedScope, int]:
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = urlsafe_b64decode(padded)
    except Exception as exc:
        raise AuthenticationError("Invalid subscription token.", code="sub_token_invalid") from exc

    if len(raw) != 54 or raw[0:1] != _TOKEN_VERSION:
        raise AuthenticationError("Invalid subscription token.", code="sub_token_invalid")

    payload = raw[:22]
    signature = raw[22:]
    expected = _sign(payload, settings)

    if not hmac.compare_digest(signature, expected):
        raise AuthenticationError("Invalid subscription token.", code="sub_token_invalid")

    scope_byte = raw[1]
    scope = _SCOPE_REVERSE.get(scope_byte)
    if scope is None:
        raise AuthenticationError("Invalid subscription token.", code="sub_token_invalid")

    user_id = uuid.UUID(bytes=raw[2:18])
    revision = int.from_bytes(raw[18:22], "big")
    return user_id, scope, revision


def _sign(payload: bytes, settings: Settings) -> bytes:
    key = settings.jwt_secret_key.get_secret_value().encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).digest()
