from __future__ import annotations

import ast
import pathlib

import pytest

from app.providers.base.exceptions import ProviderValidationError
from app.providers.base.models import ClientResult, ClientSpec
from app.providers.xray.adapter import (
    build_create_client_payload,
    build_delete_client_payload,
    build_update_client_payload,
    parse_client_response,
)
from app.providers.xray.validator import validate_xray_client_payload

VALID_UUID = "11111111-1111-1111-1111-111111111111"


def _spec(protocol="vless", client_id=VALID_UUID, email="u@x.io", **attrs):
    attributes = {"protocol": protocol}
    attributes.update(attrs)
    return ClientSpec(client_id=client_id, email=email, attributes=attributes)


def test_create_vless_payload():
    payload = build_create_client_payload(_spec("vless", flow="xtls-rprx-vision", level=2))
    assert payload["operation"] == "create"
    assert payload["protocol"] == "vless"
    c = payload["client"]
    assert c["id"] == VALID_UUID
    assert c["email"] == "u@x.io"
    assert c["flow"] == "xtls-rprx-vision"
    assert c["level"] == 2
    assert c["enable"] is True
    assert set(c.keys()) == {
        "id",
        "email",
        "flow",
        "level",
        "totalGB",
        "expiryTime",
        "enable",
        "limitIp",
        "subId",
        "tgId",
        "reset",
    }


def test_create_vmess_payload():
    payload = build_create_client_payload(_spec("vmess"))
    assert payload["protocol"] == "vmess"
    assert payload["client"]["id"] == VALID_UUID


def test_create_trojan_payload():
    payload = build_create_client_payload(_spec("trojan", client_id="secret-password"))
    assert payload["protocol"] == "trojan"
    assert payload["client"]["id"] == "secret-password"


def test_update_payload():
    payload = build_update_client_payload(_spec("vless", totalGB=1024))
    assert payload["operation"] == "update"
    assert payload["client"]["totalGB"] == 1024


def test_delete_payload():
    assert build_delete_client_payload(VALID_UUID) == {
        "operation": "delete",
        "client_id": VALID_UUID,
    }


def test_parse_response():
    raw = {"id": VALID_UUID, "email": "u@x.io", "ok": True}
    result = parse_client_response(raw)
    assert isinstance(result, ClientResult)
    assert result.client_id == VALID_UUID
    assert result.provider == "xray"
    assert result.raw == raw


def test_parse_response_nested_client():
    assert parse_client_response({"client": {"id": VALID_UUID}}).client_id == VALID_UUID


def test_invalid_protocol():
    with pytest.raises(ProviderValidationError):
        build_create_client_payload(_spec("wireguard"))


def test_missing_protocol():
    with pytest.raises(ProviderValidationError):
        build_create_client_payload(ClientSpec(client_id=VALID_UUID, email="u@x.io", attributes={}))


def test_missing_email():
    with pytest.raises(ProviderValidationError):
        build_create_client_payload(
            ClientSpec(client_id=VALID_UUID, email=None, attributes={"protocol": "vless"})
        )


def test_invalid_uuid():
    with pytest.raises(ProviderValidationError):
        build_create_client_payload(_spec("vless", client_id="not-a-uuid"))


def test_invalid_payload():
    with pytest.raises(ProviderValidationError):
        validate_xray_client_payload({"protocol": "vless", "client": {"id": VALID_UUID}})


def test_determinism():
    assert build_create_client_payload(_spec("vless")) == build_create_client_payload(
        _spec("vless")
    )


def test_no_external_layer_imports():
    pkg = pathlib.Path(__file__).resolve().parents[1]
    forbidden = ("app.services", "app.repositories", "app.db", "app.api")
    offenders = []
    for path in pkg.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                if any(m == f or m.startswith(f + ".") for f in forbidden):
                    offenders.append(f"{path.name}: {m}")
    assert offenders == [], offenders
