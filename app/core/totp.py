from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

_DIGITS = 6
_STEP = 30
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def generate_secret(length: int = 20) -> str:
    raw = secrets.token_bytes(length)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _hotp(secret: str, counter: int) -> str:
    padded = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded.upper())
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**_DIGITS)
    return str(code).zfill(_DIGITS)


def verify(secret: str, code: str, *, window: int = 1, at: float | None = None) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != _DIGITS:
        return False
    now = int((at if at is not None else time.time()) // _STEP)
    return any(
        hmac.compare_digest(_hotp(secret, now + i), code) for i in range(-window, window + 1)
    )


def provisioning_uri(secret: str, account: str, issuer: str = "XLink") -> str:
    label = quote(f"{issuer}:{account}")
    return (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits={_DIGITS}&period={_STEP}"
    )
