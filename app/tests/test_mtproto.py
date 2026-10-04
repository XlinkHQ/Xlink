"""MTProto: per-user secrets, a t.me/proxy link whose fake-TLS domain matches
the server, and a node config that cannot carry injected Python."""

from __future__ import annotations

import ast
import importlib.util
import uuid
from pathlib import Path
from types import MappingProxyType
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.exceptions import ValidationError
from app.protocols import protocols_for
from app.providers.base.models import ClientSpec, ProviderKind
from app.providers.mtproto.provider import MtprotoProvider
from app.providers.settings_validation import validate_profile_settings
from app.subscription.formats import mtproto, uri
from app.subscription.models import ProviderConfig

_spec = importlib.util.spec_from_file_location(
    "xlink_agent_mt", Path(__file__).resolve().parents[2] / "node-agent" / "xlink-agent.py"
)
agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agent)


def test_registered() -> None:
    assert protocols_for(ProviderKind.MTPROTO) == frozenset({"mtproto"})


async def test_provider_issues_stable_per_user_secret(tmp_path) -> None:  # noqa: ANN001
    p = MtprotoProvider(data_dir=str(tmp_path))
    a = await p.create_client(ClientSpec(client_id="a", email="a", attributes={}))
    b = await p.create_client(ClientSpec(client_id="b", email="b", attributes={}))
    assert len(a.raw["secret"]) == 32 and a.raw["secret"] != b.raw["secret"]
    again = await p.update_client(ClientSpec(client_id="a", email="a", attributes={}))
    assert again.raw["secret"] == a.raw["secret"]


def test_validation() -> None:
    validate_profile_settings(ProviderKind.MTPROTO, "mtproto", {"tlsDomain": "www.cloudflare.com"})
    for bad in (
        {"tlsDomain": ""},
        {"tlsDomain": "x'; import os #"},
        {"tlsDomain": "a.com", "adTag": "zz"},
    ):
        with pytest.raises(ValidationError):
            validate_profile_settings(ProviderKind.MTPROTO, "mtproto", bad)


def test_link_embeds_domain_in_secret() -> None:
    secret = "0123456789abcdef0123456789abcdef"
    cfg = ProviderConfig(
        assignment_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider_kind=ProviderKind.MTPROTO,
        provider_name="mtproto",
        protocol="mtproto",
        client_id="c",
        email="e",
        inbound_tag="mt",
        host="1.2.3.4",
        port=443,
        expires_at=None,
        traffic_limit_bytes=None,
        settings=MappingProxyType({"secret": secret, "tlsDomain": "a.com"}),
    )
    link = mtproto.render(cfg)
    q = parse_qs(urlparse(link).query)
    assert link.startswith("https://t.me/proxy?")
    assert q["secret"][0] == "ee" + secret + b"a.com".hex()
    assert uri.render_uri(cfg) == link


def test_node_config_is_inert_python() -> None:
    aid = str(uuid.uuid4())
    clients = [
        {
            "provider_kind": "mtproto",
            "assignment_id": aid,
            "settings": {"port": 8443, "tlsDomain": "a.com", "adTag": "0" * 32},
            "credentials": {"secret": "ab" * 16},
        },
        {  # junk that must be dropped, never written
            "provider_kind": "mtproto",
            "assignment_id": "__import__('os').system('x')",
            "settings": {},
            "credentials": {"secret": "') ; import os #"},
        },
    ]
    text = agent.build_mtproto_config(clients)
    tree = ast.parse(text)
    assert all(isinstance(n, ast.Assign) for n in tree.body)
    ns: dict = {}
    for node in tree.body:
        ns[node.targets[0].id] = ast.literal_eval(node.value)
    assert ns["USERS"] == {aid: "ab" * 16}
    assert ns["MODES"] == {"classic": False, "secure": False, "tls": True}
    assert ns["TLS_DOMAIN"] == "a.com" and ns["PORT"] == 8443
    with pytest.raises(RuntimeError):
        agent.build_mtproto_config([{**clients[0], "settings": {"tlsDomain": "a.com\nimport os"}}])
    assert "USERS = {}" in agent.build_mtproto_config([])


def test_traffic_deltas_survive_restart(monkeypatch) -> None:  # noqa: ANN001
    aid = str(uuid.uuid4())
    def body(up: int, down: int) -> str:
        return (
            f'mtprotoproxy_user_octets_from{{user="{aid}"}} {up}\n'
            f'mtprotoproxy_user_octets_to{{user="{aid}"}} {down}\n'
        )

    bodies = iter([body(100, 1000), body(150, 1500), body(20, 30)])

    class _Resp:
        def __init__(self, b: str) -> None:
            self.b = b.encode()

        def read(self) -> bytes:
            return self.b

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *a) -> None:  # noqa: ANN002
            pass

    monkeypatch.setattr(agent._OPENER, "open", lambda *a, **k: _Resp(next(bodies)))
    agent._mtproto_last.clear()
    first, second, third = (agent._mtproto_traffic() for _ in range(3))
    assert (first[0]["upload_bytes"], first[0]["download_bytes"]) == (100, 1000)
    assert (second[0]["upload_bytes"], second[0]["download_bytes"]) == (50, 500)
    assert (third[0]["upload_bytes"], third[0]["download_bytes"]) == (20, 30)
