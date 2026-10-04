"""Client templates: operator base documents that the clash/mihomo/sing-box
renderers inject generated servers into."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from app.core.exceptions import ValidationError
from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.user import User, UserRole
from app.subscription import templates

API = "/api/v1"
SUDO_PW = "sudo-admin-password-1234-AB!"

CLASH_TPL = """
mixed-port: 7890
dns: {enable: true, nameserver: [1.1.1.1]}
proxy-groups:
  - {name: Auto, type: url-test, url: "https://cp.cloudflare.com", interval: 300, proxies: ["{ALL}"]}
  - {name: Select, type: select, proxies: [Auto, "{ALL}", DIRECT]}
rules:
  - GEOIP,IR,DIRECT
  - MATCH,Select
"""


def test_apply_clash_keeps_template_and_expands_all() -> None:
    doc = templates.apply_clash(templates.parse("clash", CLASH_TPL), [{"name": "a"}, {"name": "b"}])
    assert doc["mixed-port"] == 7890 and doc["dns"]["enable"] is True
    assert doc["proxies"] == [{"name": "a"}, {"name": "b"}]
    assert doc["proxy-groups"][0]["proxies"] == ["a", "b"]
    assert doc["proxy-groups"][1]["proxies"] == ["Auto", "a", "b", "DIRECT"]
    assert doc["rules"][0] == "GEOIP,IR,DIRECT"


def test_apply_singbox_prepends_and_expands() -> None:
    base = templates.parse(
        "singbox",
        json.dumps(
            {
                "dns": {"servers": []},
                "outbounds": [
                    {"type": "selector", "tag": "proxy", "outbounds": ["{ALL}"]},
                    {"type": "direct", "tag": "direct"},
                ],
            }
        ),
    )
    doc = templates.apply_singbox(base, [{"type": "vless", "tag": "n1"}])
    assert [o["tag"] for o in doc["outbounds"]] == ["n1", "proxy", "direct"]
    assert doc["outbounds"][1]["outbounds"] == ["n1"]
    assert "dns" in doc


@pytest.mark.parametrize(
    ("fmt", "content"),
    [
        ("clash", "- just a list"),
        ("singbox", "{not json"),
        ("singbox", '{"outbounds": 3}'),
        ("xray", "{}"),
    ],
)
def test_parse_rejects_bad_templates(fmt: str, content: str) -> None:
    with pytest.raises(ValidationError):
        templates.parse(fmt, content)


def test_render_without_template_is_unchanged() -> None:
    assert templates.active("clash") is None
    with templates.use({"clash": {"a": 1}}):
        got = templates.active("clash")
        got["a"] = 2  # must be a copy
        assert templates.active("clash") == {"a": 1}
    assert templates.active("clash") is None


async def test_crud_and_single_default(app_state: AppState, client: AsyncClient) -> None:
    async with app_state.db.session() as s:
        s.add(
            User(
                username="root",
                hashed_password=hash_password(SUDO_PW),
                role=UserRole.ADMIN,
                is_sudo=True,
            )
        )
    r = await client.post(f"{API}/auth/login", json={"identifier": "root", "password": SUDO_PW})
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}

    r = await client.post(
        f"{API}/client-templates",
        headers=h,
        json={"name": "bad", "format": "singbox", "content": "{x"},
    )
    assert r.status_code in (400, 422)

    ids = []
    for name in ("one", "two"):
        r = await client.post(
            f"{API}/client-templates",
            headers=h,
            json={"name": name, "format": "clash", "content": CLASH_TPL, "is_default": True},
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    rows = (await client.get(f"{API}/client-templates", headers=h)).json()
    defaults = [row["name"] for row in rows if row["is_default"]]
    assert defaults == ["two"], "setting a new default must clear the old one"

    r = await client.post(
        f"{API}/client-templates",
        headers=h,
        json={"name": "two", "format": "clash", "content": CLASH_TPL},
    )
    assert r.status_code == 409

    r = await client.delete(f"{API}/client-templates/{ids[1]}", headers=h)
    assert r.status_code == 204


def test_renderers_use_the_active_template() -> None:
    import uuid

    import yaml

    from app.subscription.formats import clash, singbox
    from app.tests.test_subscription_renderers import _config

    cfg = _config("vless", {"uuid": str(uuid.uuid4()), "security": "tls", "network": "tcp"})
    sb_tpl = {
        "log": {"level": "warn"},
        "outbounds": [{"type": "selector", "tag": "proxy", "outbounds": ["{ALL}"]}],
    }
    with templates.use({"clash": templates.parse("clash", CLASH_TPL), "singbox": sb_tpl}):
        doc = yaml.safe_load(clash.render((cfg,)))
        sb = json.loads(singbox.render((cfg,)))
    assert doc["mixed-port"] == 7890 and len(doc["proxies"]) == 1
    assert doc["proxy-groups"][0]["proxies"] == [doc["proxies"][0]["name"]]
    assert sb["log"]["level"] == "warn"
    assert sb["outbounds"][-1]["outbounds"] == [sb["outbounds"][0]["tag"]]
    # no template → legacy document
    assert yaml.safe_load(clash.render((cfg,)))["rules"] == ["MATCH,PROXY"]
