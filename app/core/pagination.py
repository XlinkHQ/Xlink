from __future__ import annotations

import base64
import binascii
import uuid
from datetime import UTC, datetime

import orjson


def encode_cursor(created_at: datetime, id_: uuid.UUID) -> str:
    payload = orjson.dumps({"c": created_at.isoformat(), "i": str(id_)})
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        payload = orjson.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        dt = datetime.fromisoformat(payload["c"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt, uuid.UUID(payload["i"])
    except (binascii.Error, KeyError, ValueError, orjson.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination cursor.") from exc


def encode_sort_cursor(sort: str, value, id_: uuid.UUID) -> str:
    if isinstance(value, datetime):
        v = value.isoformat()
    else:
        v = value
    payload = orjson.dumps({"s": sort, "v": v, "i": str(id_)})
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_sort_cursor(cursor: str) -> tuple[str, object, uuid.UUID]:
    try:
        payload = orjson.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        return str(payload["s"]), payload.get("v"), uuid.UUID(payload["i"])
    except (binascii.Error, KeyError, ValueError, orjson.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination cursor.") from exc
