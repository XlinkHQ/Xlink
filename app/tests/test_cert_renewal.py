"""Covers the ACME renewal loop, whose issuance was made concurrent: issuance
runs in parallel but the DB writes that follow share one session and must stay
sequential and correctly paired with their certificate."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.domain.certificate import Certificate, CertificateSource
from app.repositories.certificate import CertificateRepository
from app.services.certificate_service import CertificateService

# A self-signed pair is not needed: import_manual is stubbed out in these tests,
# so renew_due is exercised without real X.509 parsing.


class _Cache:
    @property
    def client(self) -> Any:  # pragma: no cover - unused by renew_due
        raise AssertionError("renew_due must not touch the cache client directly")


async def _seed_due(session, domains: list[str]) -> list[Certificate]:
    past = datetime.now(UTC) - timedelta(days=1)
    certs = []
    for d in domains:
        c = Certificate(domain=d, source=CertificateSource.ACME, not_after=past)
        session.add(c)
        certs.append(c)
    await session.flush()
    return certs


@pytest.fixture
async def session(app_state):
    async with app_state.db.session() as s:
        yield s


async def test_renews_every_due_certificate(session, monkeypatch) -> None:
    await _seed_due(session, ["a.example.com", "b.example.com", "c.example.com"])
    svc = CertificateService(CertificateRepository(session))

    async def _issue(_cache, domain, email="", staging=False):
        return (f"cert-for-{domain}", f"key-for-{domain}")

    imported: list[tuple[str, str, str]] = []

    async def _import_manual(domain, cert_pem, key_pem):
        imported.append((domain, cert_pem, key_pem))
        return Certificate(domain=domain)

    monkeypatch.setattr("app.services.acme_issuer.issue_certificate", _issue)
    monkeypatch.setattr(svc, "import_manual", _import_manual)

    renewed = await svc.renew_due(_Cache(), email="ops@example.com", window_days=30)

    assert renewed == 3
    # Each certificate must be paired with its OWN issued material — the bug a
    # concurrent gather would introduce is cross-pairing.
    assert sorted(imported) == [
        ("a.example.com", "cert-for-a.example.com", "key-for-a.example.com"),
        ("b.example.com", "cert-for-b.example.com", "key-for-b.example.com"),
        ("c.example.com", "cert-for-c.example.com", "key-for-c.example.com"),
    ]


async def test_one_failure_does_not_block_the_others(session, monkeypatch) -> None:
    await _seed_due(session, ["ok1.example.com", "bad.example.com", "ok2.example.com"])
    svc = CertificateService(CertificateRepository(session))

    from app.services.acme_issuer import AcmeError

    async def _issue(_cache, domain, email="", staging=False):
        if domain == "bad.example.com":
            raise AcmeError("challenge failed")
        return (f"cert-{domain}", f"key-{domain}")

    async def _import_manual(domain, cert_pem, key_pem):
        return Certificate(domain=domain)

    monkeypatch.setattr("app.services.acme_issuer.issue_certificate", _issue)
    monkeypatch.setattr(svc, "import_manual", _import_manual)

    renewed = await svc.renew_due(_Cache(), email="ops@example.com", window_days=30)

    # The two healthy domains still renew; the failure is recorded, not raised.
    assert renewed == 2
    rows = await svc._repo.list_acme_due(before=datetime.now(UTC) + timedelta(days=30))
    failed = [c for c in rows if c.domain == "bad.example.com"]
    assert failed and "challenge failed" in failed[0].last_error


async def test_issuance_runs_concurrently_not_serially(session, monkeypatch) -> None:
    await _seed_due(session, [f"d{i}.example.com" for i in range(4)])
    svc = CertificateService(CertificateRepository(session))

    in_flight = 0
    peak = 0

    async def _issue(_cache, domain, email="", staging=False):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return (f"cert-{domain}", f"key-{domain}")

    async def _import_manual(domain, cert_pem, key_pem):
        return Certificate(domain=domain)

    monkeypatch.setattr("app.services.acme_issuer.issue_certificate", _issue)
    monkeypatch.setattr(svc, "import_manual", _import_manual)

    await svc.renew_due(_Cache(), email="ops@example.com", window_days=30)

    # Serial issuance would never exceed 1 concurrent request.
    assert peak > 1


async def test_concurrency_is_bounded(session, monkeypatch) -> None:
    from app.services import certificate_service as mod

    await _seed_due(session, [f"n{i}.example.com" for i in range(12)])
    svc = CertificateService(CertificateRepository(session))

    in_flight = 0
    peak = 0

    async def _issue(_cache, domain, email="", staging=False):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return (f"cert-{domain}", f"key-{domain}")

    async def _import_manual(domain, cert_pem, key_pem):
        return Certificate(domain=domain)

    monkeypatch.setattr("app.services.acme_issuer.issue_certificate", _issue)
    monkeypatch.setattr(svc, "import_manual", _import_manual)

    await svc.renew_due(_Cache(), email="ops@example.com", window_days=30)

    # The semaphore exists to stay inside ACME rate limits.
    assert peak <= mod._ACME_RENEW_CONCURRENCY


async def test_nothing_due_is_a_no_op(session, monkeypatch) -> None:
    svc = CertificateService(CertificateRepository(session))
    called = False

    async def _issue(*a, **k):
        nonlocal called
        called = True
        return ("c", "k")

    monkeypatch.setattr("app.services.acme_issuer.issue_certificate", _issue)
    assert await svc.renew_due(_Cache(), email="ops@example.com", window_days=30) == 0
    assert called is False
