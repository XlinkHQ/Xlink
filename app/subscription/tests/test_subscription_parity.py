from __future__ import annotations

import json

import pytest

from app.api.v1.routers.subscriptions import (
    _BlockedSubscriptionError,
    _detect_format,
    _match_admin_rules,
)
from app.core.lifespan import AppState
from app.repositories.app_settings import AppSettingsRepository
from app.schemas.settings import SubscriptionSettingsUpdate
from app.services.settings_service import SettingsService
from app.subscription.renderer import SubscriptionRenderer
from app.subscription.schemas import SubscriptionFormat
from app.subscription.service import SubscriptionService


def test_admin_rule_matches_format():
    rules = [{"pattern": "^MyClient", "result": "clash-meta"}]
    assert _match_admin_rules("MyClient/1.0", rules) is SubscriptionFormat.MIHOMO_YAML


def test_admin_rule_block_raises():
    rules = [{"pattern": "^BadBot", "result": "block"}]
    with pytest.raises(_BlockedSubscriptionError):
        _match_admin_rules("BadBot/9", rules)


def test_admin_rule_no_match_returns_none():
    rules = [{"pattern": "^Other", "result": "clash"}]
    assert _match_admin_rules("MyClient/1.0", rules) is None


def test_detect_format_precedence_explicit_over_rules():
    rules = [{"pattern": ".*", "result": "clash"}]

    assert _detect_format("anything", "singbox", rules) is SubscriptionFormat.SINGBOX_JSON


def test_detect_format_admin_rule_over_builtin():

    rules = [{"pattern": "(?i)^clash", "result": "clash-meta"}]
    assert _detect_format("clash-verge/2", None, rules) is SubscriptionFormat.MIHOMO_YAML


def test_detect_format_block_propagates():
    rules = [{"pattern": "(?i)curl", "result": "block"}]
    with pytest.raises(_BlockedSubscriptionError):
        _detect_format("curl/8.0", None, rules)


def test_detect_format_bad_regex_is_skipped():
    rules = [{"pattern": "([", "result": "clash"}]

    assert _detect_format("unknown-agent", None, rules) is SubscriptionFormat.BASE64


async def test_placeholder_feed_text(app_state: AppState):
    service = SubscriptionService(
        repository=None,
        generator=None,
        renderer=SubscriptionRenderer(),
        cache=app_state.cache,
    )
    feed = await service.placeholder_feed("Subscription expired", SubscriptionFormat.TEXT)
    assert len(feed.items) == 1

    assert "Subscription%20expired" in feed.items[0].uri
    assert feed.items[0].uri.startswith("vless://")


async def test_placeholder_feed_clash(app_state: AppState):
    service = SubscriptionService(
        repository=None,
        generator=None,
        renderer=SubscriptionRenderer(),
        cache=app_state.cache,
    )
    feed = await service.placeholder_feed("disabled", SubscriptionFormat.CLASH_YAML)

    assert "disabled" in feed.content


async def test_subscription_settings_roundtrip(app_state: AppState):
    async with app_state.db.session() as session:
        service = SettingsService(AppSettingsRepository(session))
        updated = await service.update_subscription(
            SubscriptionSettingsUpdate(
                shuffle_configs=True,
                placeholder_if_disabled=False,
                placeholder_remark="Out of data",
                rules=[{"pattern": "^Foo", "result": "block"}],
            )
        )
        assert updated.shuffle_configs is True
        assert updated.placeholder_if_disabled is False
        assert updated.placeholder_remark == "Out of data"
        assert updated.rules == [{"pattern": "^Foo", "result": "block"}]

        assert json.loads(updated.subscription_rules)[0]["result"] == "block"


async def test_subscription_settings_rejects_bad_regex(app_state: AppState):
    with pytest.raises(ValueError):
        SubscriptionSettingsUpdate(rules=[{"pattern": "([", "result": "clash"}])
