from __future__ import annotations

from app.subscription.page import _config_label, render_subscription_page


def test_label_uses_tag_when_present() -> None:
    assert _config_label("vless://id@h:443#My%20Server", "vless", 0, False) == "My Server"


def test_label_falls_back_to_host_when_no_tag() -> None:
    assert _config_label("vless://id@host.com:443?x=1", "vless", 0, False) == "host.com"


def test_label_ignores_tag_that_is_a_url() -> None:
    assert _config_label("vless://id@host.com:443#vless://other", "vless", 2, False) == "host.com"


def test_label_proto_fallback_when_no_host() -> None:
    assert _config_label("weirdformat", "cfg", 0, False) == "CFG · 1"


def test_page_never_shows_raw_uri_as_title() -> None:
    html = render_subscription_page(
        title="X",
        username="u",
        status="Active",
        used=10,
        total=100,
        expire_ts=None,
        sub_url="http://x/sub",
        configs=["vless://id@h:443", "vless://id@h:443#Germany"],
        support="",
    )
    assert 'rtitle">vless://' not in html
    assert ">Germany<" in html


def test_page_boxes_are_rounded() -> None:
    html = render_subscription_page(
        title="X",
        username="u",
        status="Active",
        used=10,
        total=100,
        expire_ts=None,
        sub_url="http://x/sub",
        configs=["vless://id@h:443#A"],
        support="",
    )
    assert ".card{width:100%;max-width:420px" in html
    assert "border-radius:22px" in html
    assert "border-radius:999px" in html


def test_empty_page_shows_status_message():
    html = render_subscription_page(
        title="X", username="u", status="Disabled", status_tone="muted",
        used=0, total=100, expire_ts=None, sub_url="http://x", configs=[], support="",
    )
    assert "disabled" in html.lower()
    assert "No configs yet" not in html
    assert 'class="empty"' in html


def test_nonempty_page_has_configs():
    html = render_subscription_page(
        title="X", username="u", status="Active", status_tone="ok",
        used=0, total=100, expire_ts=None, sub_url="http://x",
        configs=["vless://u@h:443#k"], support="",
    )
    assert 'class="empty"' not in html
    assert ">k<" in html
