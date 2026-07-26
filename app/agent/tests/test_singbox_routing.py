from __future__ import annotations

import json
import uuid

from app.agent.config_sync import ConfigSyncService
from app.core.lifespan import AppState
from app.domain.app_settings import SINGLETON_ID, AppSettings
from app.domain.node import Node, NodeStatus
from app.domain.outbound import Outbound
from app.domain.routing_rule import RoutingRule


async def _node(session) -> Node:
    node = Node(
        name="n1",
        slug=f"n-{uuid.uuid4().hex[:8]}",
        host="1.2.3.4",
        port=443,
        status=NodeStatus.ACTIVE,
    )
    session.add(node)
    await session.flush()
    return node


async def _set_template(session, template: dict) -> None:
    settings = AppSettings(id=SINGLETON_ID, xray_core_template=json.dumps(template))
    session.add(settings)
    await session.flush()


async def _templates(session, node) -> dict:
    return await ConfigSyncService(session)._core_templates(node.id)


async def test_singbox_gets_route_rules(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        node = await _node(session)
        await _set_template(session, {"sing-box": {"inbounds": []}})
        session.add(
            RoutingRule(
                name="block-ads",
                match_type="domain",
                match_values="ads.example.com, full:exact.example.com",
                outbound="block",
                enabled=True,
                priority=0,
            )
        )
        session.add(
            RoutingRule(
                name="direct-lan",
                match_type="ip",
                match_values="192.168.0.0/16",
                outbound="direct",
                enabled=True,
                priority=1,
            )
        )
        session.add(
            RoutingRule(
                name="port-rule",
                match_type="port",
                match_values="443, 8000-9000",
                outbound="direct",
                enabled=True,
                priority=2,
            )
        )
        await session.flush()

        templates = await _templates(session, node)
        sb = templates["sing-box"]
        route = sb["route"]
        rules = route["rules"]

        dom = next(r for r in rules if r.get("outbound") == "block")
        assert dom["domain"] == ["exact.example.com"]
        assert dom["domain_suffix"] == ["ads.example.com"]

        ip = next(r for r in rules if "ip_cidr" in r)
        assert ip["ip_cidr"] == ["192.168.0.0/16"]
        assert ip["outbound"] == "direct"

        port = next(r for r in rules if "port" in r or "port_range" in r)
        assert port["port"] == [443]
        assert port["port_range"] == ["8000:9000"]

        tags = {o["tag"] for o in sb["outbounds"]}
        assert "block" in tags
        assert "direct" in tags
        assert route["final"] == "direct"
        block_ob = next(o for o in sb["outbounds"] if o["tag"] == "block")
        assert block_ob["type"] == "block"


async def test_singbox_geosite_selector_dropped(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        node = await _node(session)
        await _set_template(session, {"sing-box": {"inbounds": []}})
        session.add(
            RoutingRule(
                name="mixed",
                match_type="domain",
                match_values="geosite:google, real.example.com",
                outbound="direct",
                enabled=True,
            )
        )
        session.add(
            RoutingRule(
                name="only-geo",
                match_type="domain",
                match_values="geosite:netflix",
                outbound="direct",
                enabled=True,
                priority=5,
            )
        )
        await session.flush()

        sb = (await _templates(session, node))["sing-box"]
        rules = sb["route"]["rules"]
        assert len(rules) == 1
        assert rules[0]["domain_suffix"] == ["real.example.com"]
        assert "geosite:google" not in json.dumps(rules)


async def test_singbox_dangling_outbound_rule_dropped(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        node = await _node(session)
        await _set_template(session, {"sing-box": {"inbounds": []}})
        session.add(
            RoutingRule(
                name="to-ghost",
                match_type="domain",
                match_values="x.example.com",
                outbound="ghost",
                enabled=True,
            )
        )
        await session.flush()

        sb = (await _templates(session, node))["sing-box"]
        rules = sb["route"]["rules"]
        assert all(r.get("outbound") != "ghost" for r in rules)
        assert sb["route"]["final"] == "direct"


async def test_singbox_custom_outbound_translated(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        node = await _node(session)
        await _set_template(session, {"sing-box": {"inbounds": []}})
        session.add(
            Outbound(
                tag="relay",
                type="trojan",
                settings={"address": "5.6.7.8:443", "password": "secret"},
                enabled=True,
            )
        )
        session.add(
            RoutingRule(
                name="via-relay",
                match_type="domain",
                match_values="via.example.com",
                outbound="relay",
                enabled=True,
            )
        )
        await session.flush()

        sb = (await _templates(session, node))["sing-box"]
        relay = next((o for o in sb["outbounds"] if o["tag"] == "relay"), None)
        assert relay is not None
        assert relay["type"] == "trojan"
        assert relay["server"] == "5.6.7.8"
        assert relay["server_port"] == 443
        assert any(r.get("outbound") == "relay" for r in sb["route"]["rules"])


async def test_singbox_unsupported_custom_outbound_drops_rule(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        node = await _node(session)
        await _set_template(session, {"sing-box": {"inbounds": []}})
        session.add(
            Outbound(
                tag="xray-only",
                type="custom",
                settings={"raw": {"protocol": "vless", "tag": "x"}},
                enabled=True,
            )
        )
        session.add(
            RoutingRule(
                name="via-xray-only",
                match_type="domain",
                match_values="y.example.com",
                outbound="xray-only",
                enabled=True,
            )
        )
        await session.flush()

        sb = (await _templates(session, node))["sing-box"]
        assert all(o["tag"] != "xray-only" for o in sb["outbounds"])
        assert all(r.get("outbound") != "xray-only" for r in sb["route"]["rules"])


async def test_xray_path_unchanged_when_no_singbox(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        node = await _node(session)
        await _set_template(session, {"xray": {"inbounds": []}})
        session.add(
            RoutingRule(
                name="block-ads",
                match_type="domain",
                match_values="ads.example.com",
                outbound="block",
                enabled=True,
            )
        )
        await session.flush()

        templates = await _templates(session, node)
        assert "sing-box" not in templates
        xray = templates["xray"]
        rule = xray["routing"]["rules"][0]
        assert rule["type"] == "field"
        assert rule["outboundTag"] == "block"
        assert rule["domain"] == ["ads.example.com"]
