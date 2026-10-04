from __future__ import annotations

import gzip

import pytest

from app.api.v1.routers.backup import _bounded_gunzip


def test_gzip_bomb_is_refused() -> None:
    bomb = gzip.compress(b"\0" * (20 * 1024 * 1024))
    with pytest.raises(ValueError):
        _bounded_gunzip(bomb, 1024 * 1024)


def test_normal_gzip_round_trips() -> None:
    raw = b"CREATE TABLE x();\n" * 5000
    assert _bounded_gunzip(gzip.compress(raw), 10 * 1024 * 1024) == raw
