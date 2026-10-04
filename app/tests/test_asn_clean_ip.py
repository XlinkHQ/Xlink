"""Per-ISP clean CDN addresses: ASN lookup, host-map validation, override
substitution and cache separation."""

from __future__ import annotations

import gzip
import uuid

import pytest

from app.core.exceptions import ValidationError
from app.schemas.inbound_host import validate_asn_addresses
from app.services.asn_lookup import AsnDatabase
from app.subscription.schemas import FeedRequest, FeedScope
from app.subscription.service import _apply_asn_addresses


@pytest.fixture
def asn_dir(tmp_path):  # noqa: ANN001, ANN201
    with gzip.open(tmp_path / "ip2asn-v4.tsv.gz", "wt") as fh:
        fh.write("1.0.0.0\t1.0.0.255\t13335\tUS\tCLOUDFLARENET\n")
        fh.write("2.176.0.0\t2.191.255.255\t58224\tIR\tTCI\n")
        fh.write("10.0.0.0\t10.255.255.255\t0\tNone\tNot routed\n")
    with gzip.open(tmp_path / "ip2asn-v6.tsv.gz", "wt") as fh:
        fh.write("2001:4860::\t2001:4860:ffff:ffff:ffff:ffff:ffff:ffff\t15169\tUS\tGOOGLE\n")
    return str(tmp_path)


async def test_lookup(asn_dir: str) -> None:
    db = AsnDatabase(asn_dir)
    assert await db.lookup("2.180.1.2") == 58224
    assert await db.lookup("1.0.0.1") == 13335
    assert await db.lookup("10.1.1.1") is None  # AS0
    assert await db.lookup("3.3.3.3") is None
    assert await db.lookup("2001:4860:4860::8888") == 15169
    assert await db.lookup("::ffff:2.176.0.9") == 58224
    assert await db.lookup("garbage") is None


async def test_missing_dataset_is_inert(tmp_path) -> None:  # noqa: ANN001
    assert await AsnDatabase(str(tmp_path)).lookup("2.176.0.1") is None


def test_validation_normalises_and_rejects() -> None:
    assert validate_asn_addresses({"AS58224": ["104.16.1.1", "cdn.example.com"]}) == {
        "58224": ["104.16.1.1", "cdn.example.com"]
    }
    assert validate_asn_addresses({}) is None
    for bad in ({"ASX": ["1.1.1.1"]}, {"58224": []}, {"58224": ["not a host!"]}):
        with pytest.raises(ValidationError):
            validate_asn_addresses(bad)


def test_override_substitution() -> None:
    pid = uuid.uuid4()
    overrides = {
        pid: [
            {"address": "cdn.default.com", "asn_addresses": {"58224": ["104.16.9.9"]}},
            {"address": "plain.com"},
        ]
    }
    tci = _apply_asn_addresses(overrides, 58224)[pid]
    other = _apply_asn_addresses(overrides, 44244)[pid]
    none = _apply_asn_addresses(overrides, None)[pid]
    assert tci[0]["address"] == "104.16.9.9"
    assert other[0]["address"] == "cdn.default.com" and none[0]["address"] == "cdn.default.com"
    assert all("asn_addresses" not in h for h in tci + other + none)
    assert tci[1] == {"address": "plain.com"}


def test_feed_request_carries_asn() -> None:
    a = FeedRequest(scope=FeedScope.USER, subject_id=uuid.uuid4(), client_asn=58224)
    assert a.client_asn == 58224
