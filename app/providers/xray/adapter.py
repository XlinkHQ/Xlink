from __future__ import annotations

from typing import Any

from app.providers.base.models import ClientResult, ClientSpec
from app.providers.xray.exceptions import XrayPayloadError
from app.providers.xray.payloads import (
    CLIENT_DEFAULTS,
    OPERATION_CREATE,
    OPERATION_DELETE,
    OPERATION_UPDATE,
    PROVIDER_NAME,
)
from app.providers.xray.stream import build_stream_settings
from app.providers.xray.validator import validate_spec, validate_xray_client_payload


def _build_client(spec: ClientSpec) -> dict[str, Any]:
    attrs = spec.attributes
    client: dict[str, Any] = {
        "id": str(spec.client_id),
        "email": spec.email.strip() if spec.email else "",
    }
    for field, default in CLIENT_DEFAULTS.items():
        value = attrs.get(field, default)
        try:
            if isinstance(default, bool):
                if isinstance(value, str):
                    client[field] = value.strip().lower() in ("true", "1", "yes", "on")
                else:
                    client[field] = bool(value)
            elif isinstance(default, int):
                client[field] = int(value)
            else:
                client[field] = str(value)
        except (TypeError, ValueError) as exc:
            raise XrayPayloadError(f"Invalid value for field '{field}': {value!r}") from exc
    return client


def _build_client_payload(spec: ClientSpec, operation: str) -> dict[str, Any]:
    protocol = validate_spec(spec)
    payload = {
        "operation": operation,
        "protocol": protocol,
        "client": _build_client(spec),
        "streamSettings": build_stream_settings(spec.attributes),
    }
    validate_xray_client_payload(payload)
    return payload


def build_create_client_payload(spec: ClientSpec) -> dict[str, Any]:
    return _build_client_payload(spec, OPERATION_CREATE)


def build_update_client_payload(spec: ClientSpec) -> dict[str, Any]:
    return _build_client_payload(spec, OPERATION_UPDATE)


def build_delete_client_payload(client_id: str) -> dict[str, Any]:
    if not isinstance(client_id, str) or not client_id.strip():
        raise XrayPayloadError("client_id is required for delete.")
    return {"operation": OPERATION_DELETE, "client_id": client_id}


def parse_client_response(raw: dict) -> ClientResult:
    if not isinstance(raw, dict):
        raise XrayPayloadError("Response must be a dict.")
    client_id = raw.get("id")
    if client_id is None:
        client = raw.get("client")
        if isinstance(client, dict):
            client_id = client.get("id")
    if client_id is None:
        client_id = raw.get("client_id")
    if not isinstance(client_id, str) or not client_id.strip():
        raise XrayPayloadError("Response is missing a client id.")
    return ClientResult(client_id=client_id, provider=PROVIDER_NAME, raw=dict(raw))
