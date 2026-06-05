from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.providers.base.exceptions import ClientAlreadyExistsError, ClientNotFoundError


class XrayTransport(ABC):
    @abstractmethod
    async def send(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    async def health(self) -> bool: ...

    async def close(self) -> None:
        return None


class InMemoryTransport(XrayTransport):
    def __init__(self) -> None:
        self._clients: dict[str, dict[str, Any]] = {}
        self._healthy = True

    def set_healthy(self, healthy: bool) -> None:
        self._healthy = healthy

    async def health(self) -> bool:
        return self._healthy

    async def send(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation == "create":
            client = payload["client"]
            if client["id"] in self._clients:
                raise ClientAlreadyExistsError(
                    f"Client '{client['id']}' already exists.",
                    details={"client_id": client["id"]},
                )
            self._clients[client["id"]] = client
            return dict(client)
        if operation == "update":
            client = payload["client"]
            if client["id"] not in self._clients:
                raise ClientNotFoundError(
                    f"Client '{client['id']}' was not found.",
                    details={"client_id": client["id"]},
                )
            self._clients[client["id"]] = client
            return dict(client)
        if operation == "delete":
            client_id = payload["client_id"]
            if client_id not in self._clients:
                raise ClientNotFoundError(
                    f"Client '{client_id}' was not found.",
                    details={"client_id": client_id},
                )
            self._clients.pop(client_id)
            return {"client_id": client_id}
        if operation == "get":
            client_id = payload["client_id"]
            stored = self._clients.get(client_id)
            if stored is None:
                raise ClientNotFoundError(
                    f"Client '{client_id}' was not found.",
                    details={"client_id": client_id},
                )
            return dict(stored)
        return {}
