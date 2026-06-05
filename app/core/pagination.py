from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime

import orjson


def encode_cursor(created_at: datetime, id_: uuid.UUID) -> str:
    payload = orjson.dumps({"c": created_at.isoformat(), "i": str(id_)})
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        payload = orjson.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        return datetime.fromisoformat(payload["c"]), uuid.UUID(payload["i"])
    except (binascii.Error, KeyError, ValueError, orjson.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination cursor.") from exc
