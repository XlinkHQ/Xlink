from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.dependencies.auth import SudoAdminUser
from app.dependencies.core import CacheDep
from app.dependencies.services import CertificateServiceDep
from app.schemas.certificate import (
    CertificateAcmeRequest,
    CertificateImport,
    CertificateRead,
)

router = APIRouter(prefix="/certificates", tags=["certificates"])


@router.get("", response_model=list[CertificateRead])
async def list_certificates(
    _admin: SudoAdminUser,
    certs: CertificateServiceDep,
) -> list[CertificateRead]:
    return [CertificateRead.model_validate(c) for c in await certs.list()]


@router.post("", response_model=CertificateRead, status_code=status.HTTP_201_CREATED)
async def import_certificate(
    payload: CertificateImport,
    _admin: SudoAdminUser,
    certs: CertificateServiceDep,
) -> CertificateRead:
    cert = await certs.import_manual(payload.domain, payload.cert_pem, payload.key_pem)
    return CertificateRead.model_validate(cert)


@router.post("/acme", response_model=CertificateRead, status_code=status.HTTP_201_CREATED)
async def request_acme_certificate(
    payload: CertificateAcmeRequest,
    admin: SudoAdminUser,
    certs: CertificateServiceDep,
    cache: CacheDep,
) -> CertificateRead:
    cert = await certs.request_acme(payload.domain, cache, email=admin.email or "")
    return CertificateRead.model_validate(cert)


@router.delete("/{cert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certificate(
    cert_id: uuid.UUID,
    _admin: SudoAdminUser,
    certs: CertificateServiceDep,
) -> None:
    await certs.delete(cert_id)
