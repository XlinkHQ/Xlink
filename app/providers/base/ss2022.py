"""Shadowsocks 2022 (SIP022) key rules, shared by every layer.

2022 ciphers take raw keys, not passwords: base64 of exactly 16 bytes for
aes-128-gcm and 32 bytes otherwise. Multi-user inbounds also need a server
PSK (``serverPassword`` on the profile); a client then authenticates with
``"<serverPassword>:<userKey>"``.
"""

from __future__ import annotations

import base64
import binascii
import secrets

DEFAULT_METHOD = "2022-blake3-aes-256-gcm"


def is_2022(method: str | None) -> bool:
    return str(method or "").strip().lower().startswith("2022-")


def key_bytes(method: str) -> int:
    return 16 if str(method).strip().lower() == "2022-blake3-aes-128-gcm" else 32


def new_key(method: str = DEFAULT_METHOD) -> str:
    return base64.b64encode(secrets.token_bytes(key_bytes(method))).decode("ascii")


def key_ok(value: str, method: str) -> bool:
    try:
        raw = base64.b64decode(str(value).strip(), validate=True)
    except (binascii.Error, ValueError):
        return False
    return len(raw) == key_bytes(method)


def method_for(protocol: str, settings: dict) -> str:
    default = DEFAULT_METHOD if protocol == "shadowsocks2022" else "aes-256-gcm"
    return str(settings.get("method") or default).strip().lower()
