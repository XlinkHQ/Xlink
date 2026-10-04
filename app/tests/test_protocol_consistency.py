"""Cross-layer protocol rules: what the panel accepts, the node serves and the
client is told must agree (ss2022 keys, REALITY keys, ALPN, TUIC, obfs)."""

from __future__ import annotations

import base64
import importlib.util
import uuid
from pathlib import Path
from types import MappingProxyType

import pytest

from app.core.exceptions import ValidationError
from app.providers.base import ss2022
from app.providers.base.models import ProviderKind
from app.providers.settings_validation import validate_profile_settings
from app.subscription.formats import clash, shadowsocks, singbox
from app.subscription.models import ProviderConfig

_spec = importlib.util.spec_from_file_location(
    "xlink_agent", Path(__file__).resolve().parents[2] / "node-agent" / "xlink-agent.py"
)
agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agent)


def _cfg(protocol: str, settings: dict, password: str | None = None) -> ProviderConfig:
    s = dict(settings)
    if password:
        s["password"] = password
    return ProviderConfig(
        assignment_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider_kind=ProviderKind.SING_BOX,
        provider_name="p",
        protocol=protocol,
        client_id="cid",
        email="e@x",
        inbound_tag="in",
        host="example.com",
        port=443,
        expires_at=None,
        traffic_limit_bytes=None,
        settings=MappingProxyType(s),
    )


def test_ss2022_requires_valid_server_key() -> None:
    with pytest.raises(ValidationError):
        validate_profile_settings(ProviderKind.SING_BOX, "shadowsocks2022", {"port": 8388})
    with pytest.raises(ValidationError):
        validate_profile_settings(
            ProviderKind.SING_BOX, "shadowsocks2022", {"serverPassword": "short"}
        )
    validate_profile_settings(
        ProviderKind.SING_BOX, "shadowsocks2022", {"serverPassword": ss2022.new_key()}
    )
    m = "2022-blake3-aes-128-gcm"
    assert len(base64.b64decode(ss2022.new_key(m))) == 16
    with pytest.raises(ValidationError):  # 32-byte key on a 16-byte cipher
        validate_profile_settings(
            ProviderKind.XRAY, "shadowsocks", {"method": m, "serverPassword": ss2022.new_key()}
        )


def test_ss2022_clients_get_server_and_user_key_everywhere() -> None:
    server, user = ss2022.new_key(), ss2022.new_key()
    cfg = _cfg("shadowsocks2022", {"serverPassword": server}, password=user)
    want = f"{server}:{user}"
    sb = singbox._outbounds(cfg)[0]
    assert sb["password"] == want
    proxy = clash.build_proxy(cfg, allowed=clash.MIHOMO_PROTOCOLS)
    assert proxy["password"] == want
    userinfo = shadowsocks.render(cfg).split("://", 1)[1].split("@", 1)[0]
    decoded = base64.urlsafe_b64decode(userinfo + "=" * (-len(userinfo) % 4)).decode()
    assert decoded == f"2022-blake3-aes-256-gcm:{want}"


def test_agent_sets_server_psk_on_both_cores() -> None:
    server, user = ss2022.new_key(), ss2022.new_key()
    cl = {
        "protocol": "shadowsocks2022",
        "assignment_id": "a1",
        "settings": {"port": 8388, "serverPassword": server},
        "credentials": {"password": user},
    }
    xray = agent.build_xray_config([cl])
    ib = next(i for i in xray["inbounds"] if i.get("port") == 8388)
    assert ib["settings"]["password"] == server
    assert ib["settings"]["clients"][0]["password"] == user
    sb = agent.build_singbox_config([cl])
    sib = next(i for i in sb["inbounds"] if i.get("listen_port") == 8388)
    assert sib["password"] == server


def _reality_pair() -> tuple[str, str]:
    from app.api.v1.routers.profiles import _x25519

    return _x25519(urlsafe=True)


def test_reality_key_pair_and_short_id_are_checked() -> None:
    priv, pub = _reality_pair()
    base = {"security": "reality", "sni": "www.microsoft.com", "privateKey": priv}
    validate_profile_settings(
        ProviderKind.XRAY, "vless", {**base, "publicKey": pub, "shortId": "ab12"}
    )
    _, other_pub = _reality_pair()
    with pytest.raises(ValidationError):
        validate_profile_settings(ProviderKind.XRAY, "vless", {**base, "publicKey": other_pub})
    for bad in ("abc", "zz", "0" * 18):
        with pytest.raises(ValidationError):
            validate_profile_settings(
                ProviderKind.XRAY, "vless", {**base, "publicKey": pub, "shortId": bad}
            )


def test_singbox_renders_reality_with_empty_short_id() -> None:
    _, pub = _reality_pair()
    cfg = _cfg(
        "vless",
        {"security": "reality", "sni": "a.com", "publicKey": pub, "uuid": str(uuid.uuid4())},
    )
    out = singbox._outbounds(cfg)[0]
    assert out["tls"]["reality"]["short_id"] == ""


def test_alpn_and_tuic_validation() -> None:
    with pytest.raises(ValidationError):
        validate_profile_settings(ProviderKind.SING_BOX, "vless", {"alpn": "h2,spdy/3"})
    with pytest.raises(ValidationError):
        validate_profile_settings(ProviderKind.SING_BOX, "tuic", {"congestionControl": "reno"})


def test_agent_tuic_congestion_and_alpn() -> None:
    cl = {
        "protocol": "tuic",
        "assignment_id": "a1",
        "settings": {"port": 9443, "sni": "a.com", "congestionControl": "cubic"},
        "credentials": {"uuid": str(uuid.uuid4()), "password": "p"},
    }
    sb = agent.build_singbox_config([cl])
    ib = next(i for i in sb["inbounds"] if i.get("listen_port") == 9443)
    assert ib["congestion_control"] == "cubic"
    assert ib["tls"]["alpn"] == ["h3"]


def test_shadowtls_detour_port_is_stable() -> None:
    def st(port: int, aid: str) -> dict:
        return {
            "protocol": "shadowtls",
            "assignment_id": aid,
            "settings": {"port": port, "sni": "a.com"},
            "credentials": {"password": "p" + aid},
        }

    def detour_ports(clients: list[dict]) -> dict[int, int]:
        sb = agent.build_singbox_config(clients)
        by_tag = {i["tag"]: i for i in sb["inbounds"]}
        return {
            i["listen_port"]: by_tag[i["detour"]]["listen_port"]
            for i in sb["inbounds"]
            if i.get("type") == "shadowtls"
        }

    alone = detour_ports([st(8443, "b")])
    both = detour_ports([st(7443, "a"), st(8443, "b")])
    assert both[8443] == alone[8443], "adding a profile must not move another's detour"


async def test_hysteria_obfs_must_agree_per_node(app_state) -> None:  # noqa: ANN001
    from app.domain.node import Node, NodeStatus
    from app.repositories.node import NodeRepository
    from app.repositories.profile import ProfileRepository
    from app.schemas.profile import ProfileCreate
    from app.services.profile_service import ProfileService

    async with app_state.db.session() as session:
        node = Node(name="h", slug="h-node", host="1.2.3.4", port=443, status=NodeStatus.ACTIVE)
        session.add(node)
        await session.flush()
        svc = ProfileService(
            ProfileRepository(session), NodeRepository(session), app_state.providers
        )

        def mk(slug: str, pw: str) -> ProfileCreate:
            return ProfileCreate(
                name=slug,
                slug=slug,
                provider_kind=ProviderKind.HYSTERIA,
                node_id=node.id,
                protocol="hysteria2",
                settings={"port": 443, "sni": "a.com", "obfs": "salamander", "obfsPassword": pw},
            )

        await svc.create(mk("hy-a", "one"))
        await svc.create(mk("hy-b", "one"))
        with pytest.raises(ValidationError):
            await svc.create(mk("hy-c", "two"))
