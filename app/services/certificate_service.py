from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import NameOID

from app.core.cache import CacheProtocol
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.certificate import Certificate, CertificateSource, CertificateStatus
from app.repositories.certificate import CertificateRepository


def _parse_cert(cert_pem: str) -> x509.Certificate:
    try:
        return x509.load_pem_x509_certificate(cert_pem.encode())
    except ValueError as exc:
        raise ValidationError(
            "Invalid certificate PEM.", code="invalid_certificate"
        ) from exc


def _parse_key(key_pem: str) -> object:
    try:
        return serialization.load_pem_private_key(key_pem.encode(), password=None)
    except (ValueError, TypeError) as exc:
        raise ValidationError("Invalid private key PEM.", code="invalid_key") from exc


def _key_matches_cert(cert: x509.Certificate, key: object) -> bool:
    cert_pub = cert.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    if isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey, ed25519.Ed25519PrivateKey)):
        key_pub = key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return cert_pub == key_pub
    return False


def _domains_of(cert: x509.Certificate) -> list[str]:
    names: list[str] = []
    try:
        cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if cn:
            names.append(str(cn[0].value))
    except (IndexError, ValueError):
        pass
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        names.extend(san.value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        pass
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _issuer_of(cert: x509.Certificate) -> str:
    try:
        org = cert.issuer.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
        if org:
            return str(org[0].value)
        cn = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
        if cn:
            return str(cn[0].value)
    except (IndexError, ValueError):
        pass
    return ""


class CertificateService:
    def __init__(self, repo: CertificateRepository) -> None:
        self._repo = repo

    async def list(self) -> list[Certificate]:
        return await self._repo.list_all()

    async def get(self, cert_id: uuid.UUID) -> Certificate:
        cert = await self._repo.get(cert_id)
        if cert is None:
            raise NotFoundError("Certificate not found.", code="certificate_not_found")
        return cert

    async def import_manual(self, domain: str, cert_pem: str, key_pem: str) -> Certificate:
        domain = domain.strip().lower()
        if not domain:
            raise ValidationError("Domain is required.", code="domain_required")
        cert = _parse_cert(cert_pem)
        key = _parse_key(key_pem)
        if not _key_matches_cert(cert, key):
            raise ValidationError(
                "Private key does not match the certificate.", code="key_mismatch"
            )

        not_before = cert.not_valid_before_utc
        not_after = cert.not_valid_after_utc
        cert_domains = _domains_of(cert)
        if cert_domains and domain not in {d.lower() for d in cert_domains}:
            raise ValidationError(
                f"Certificate is for {', '.join(cert_domains)}, not {domain}.",
                code="domain_mismatch",
            )

        existing = await self._repo.get_by_domain(domain)
        if existing is None:
            existing = Certificate(domain=domain)
            await self._repo.add(existing)
        existing.source = CertificateSource.MANUAL
        existing.status = CertificateStatus.ACTIVE
        existing.cert_pem = cert_pem.strip() + "\n"
        existing.key_pem = key_pem.strip() + "\n"
        existing.issuer = _issuer_of(cert)
        existing.not_before = not_before
        existing.not_after = not_after
        existing.last_error = ""
        existing.renewed_at = datetime.now(UTC)
        await self._repo.session.flush()
        return existing

    async def delete(self, cert_id: uuid.UUID) -> None:
        cert = await self.get(cert_id)
        await self._repo.delete(cert)

    async def renew_due(
        self,
        cache: CacheProtocol,
        *,
        email: str,
        staging: bool = False,
        window_days: int = 30,
        now: datetime | None = None,
    ) -> int:
        from datetime import timedelta

        from app.services.acme_issuer import AcmeError, issue_certificate

        reference = now or datetime.now(UTC)
        before = reference + timedelta(days=window_days)
        due = await self._repo.list_acme_due(before=before)
        renewed = 0
        for cert in due:
            try:
                fullchain_pem, key_pem = await issue_certificate(
                    cache, cert.domain, email=email, staging=staging
                )
            except AcmeError as exc:
                cert.last_error = str(exc)[:500]
                await self._repo.session.flush()
                continue
            result = await self.import_manual(cert.domain, fullchain_pem, key_pem)
            result.source = CertificateSource.ACME
            await self._repo.session.flush()
            renewed += 1
        return renewed

    async def request_acme(
        self, domain: str, cache: CacheProtocol, email: str = "", staging: bool = False
    ) -> Certificate:
        from app.services.acme_issuer import AcmeError, issue_certificate

        domain = domain.strip().lower()
        if not domain:
            raise ValidationError("Domain is required.", code="domain_required")
        if domain in ("localhost",) or domain.replace(".", "").isdigit():
            raise ValidationError(
                "ACME requires a public domain name (not an IP or localhost).",
                code="acme_invalid_domain",
            )
        existing = await self._repo.get_by_domain(domain)
        if existing is None:
            existing = Certificate(domain=domain, source=CertificateSource.ACME)
            await self._repo.add(existing)
        existing.source = CertificateSource.ACME
        existing.status = CertificateStatus.PENDING
        existing.last_error = ""
        await self._repo.session.commit()

        try:
            fullchain_pem, key_pem = await issue_certificate(
                cache, domain, email=email, staging=staging
            )
        except AcmeError as exc:
            existing.status = CertificateStatus.ERROR
            existing.last_error = str(exc)[:500]
            await self._repo.session.flush()
            raise ValidationError(
                f"ACME issuance failed: {exc}", code="acme_failed"
            ) from exc

        result = await self.import_manual(domain, fullchain_pem, key_pem)
        result.source = CertificateSource.ACME
        await self._repo.session.flush()
        return result
