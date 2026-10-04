"""AmneziaWG: params generated, validated, carried to the client config and
applied on the node through awg-quick, with S1/S2/H1-H4 identical on both."""

from __future__ import annotations

import base64
import importlib.util
import uuid
from pathlib import Path
from types import MappingProxyType

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from app.core.exceptions import ValidationError
from app.providers.base import amneziawg
from app.providers.base.models import ProviderKind
from app.providers.settings_validation import validate_profile_settings
from app.subscription.formats import wireguard
from app.subscription.models import ProviderConfig

_spec = importlib.util.spec_from_file_location(
    "xlink_agent_awg", Path(__file__).resolve().parents[2] / "node-agent" / "xlink-agent.py"
)
agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agent)


def _pair() -> tuple[str, str]:
    k = x25519.X25519PrivateKey.generate()
    raw = serialization.Encoding.Raw
    priv = k.private_bytes(raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = k.public_key().public_bytes(raw, serialization.PublicFormat.Raw)
    return base64.b64encode(priv).decode(), base64.b64encode(pub).decode()


def _server_settings(params: dict) -> dict:
    priv, pub = _pair()
    return {
        "port": 51820,
        "address": "10.8.0.1/24",
        "privateKey": priv,
        "publicKey": pub,
        "amnezia": "true",
        **params,
    }


def test_generated_params_are_valid_and_random() -> None:
    a, b = amneziawg.generate(), amneziawg.generate()
    assert amneziawg.problems(a) == [] and amneziawg.problems(b) == []
    assert a != b


def test_validation_rejects_bad_params() -> None:
    good = amneziawg.generate()
    validate_profile_settings(ProviderKind.WIREGUARD, "wireguard", _server_settings(good))
    for bad in (
        {"H2": good["H1"]},
        {"S2": str(int(good["S1"]) + 56)},
        {"Jmin": "500", "Jmax": "100"},
        {"Jc": ""},
    ):
        with pytest.raises(ValidationError):
            validate_profile_settings(
                ProviderKind.WIREGUARD, "wireguard", _server_settings({**good, **bad})
            )


def test_client_and_server_carry_the_same_params() -> None:
    params = amneziawg.generate()
    server = _server_settings(params)
    cpriv, _ = _pair()
    cfg = ProviderConfig(
        assignment_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider_kind=ProviderKind.WIREGUARD,
        provider_name="wg",
        protocol="wireguard",
        client_id="c",
        email="e",
        inbound_tag="wg",
        host="1.2.3.4",
        port=51820,
        expires_at=None,
        traffic_limit_bytes=None,
        settings=MappingProxyType(
            {**server, "privateKey": cpriv, "peerPublicKey": server["publicKey"]}
        ),
    )
    client_conf = wireguard.render_one(cfg)
    clients = [
        {
            "provider_kind": "wireguard",
            "assignment_id": "a1",
            "settings": server,
            "credentials": {"public_key": _pair()[1], "address": "10.8.0.2/32"},
        }
    ]
    assert agent._effective_core(clients[0]) == "amneziawg"
    server_conf = agent.build_amneziawg_config(clients)
    for key in amneziawg.PARAMS:
        line = f"{key} = {params[key]}"
        assert line in client_conf
        assert line in server_conf
    # params sit inside [Interface], before the first [Peer]
    assert server_conf.index("H4 = ") < server_conf.find("[Peer]") or "[Peer]" not in server_conf


def test_plain_wireguard_is_untouched() -> None:
    s = _server_settings(amneziawg.generate())
    s["amnezia"] = "false"
    cl = {"provider_kind": "wireguard", "settings": s}
    assert agent._effective_core(cl) == "wireguard"
    assert "Jc =" not in agent.build_wireguard_config([cl])
