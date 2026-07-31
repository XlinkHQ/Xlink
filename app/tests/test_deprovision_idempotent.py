from __future__ import annotations

import pytest

from app.providers.base.exceptions import ClientNotFoundError, ProviderError
from app.services.client_assignment_service import ClientAssignmentService


class _AbsentProvider:
    async def delete_client(self, client_id: str) -> None:
        raise ClientNotFoundError(details={"client_id": client_id})


class _FailingProvider:
    async def delete_client(self, client_id: str) -> None:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_deprovision_ignores_absent_client() -> None:
    svc = ClientAssignmentService.__new__(ClientAssignmentService)
    await svc._deprovision(_AbsentProvider(), "gone")


@pytest.mark.asyncio
async def test_deprovision_still_raises_on_real_failure() -> None:
    svc = ClientAssignmentService.__new__(ClientAssignmentService)
    with pytest.raises(ProviderError):
        await svc._deprovision(_FailingProvider(), "c1")
