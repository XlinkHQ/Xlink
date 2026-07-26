from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.agent.ingest_limit import enforce_ingest_quota
from app.core.authz import Permission, authorize
from app.core.exceptions import AuthenticationError
from app.core.security import TokenType, decode_token
from app.dependencies.core import CacheDep, DatabaseDep, SettingsDep
from app.dependencies.services import AuthServiceDep, NodeAgentServiceDep

AgentServiceForQuota = NodeAgentServiceDep
from app.domain.api_key import ApiKey
from app.domain.user import User


def _set_actor(request: Request, user: User) -> None:
    request.state.actor_id = str(user.id)
    request.state.actor_username = user.username


_bearer = HTTPBearer(auto_error=False, description="JWT access token")
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


async def _user_from_api_key(
    api_key: str, database: DatabaseDep, auth_service: AuthServiceDep
) -> User:
    parts = api_key.split("_")
    if len(parts) < 3 or parts[0] != "xlk":
        raise AuthenticationError("Invalid API key.", code="api_key_invalid")
    prefix = parts[1]
    token_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    async with database.session() as session:
        candidates = (
            (await session.execute(select(ApiKey).where(ApiKey.prefix == prefix))).scalars().all()
        )
        row = next(
            (
                c
                for c in candidates
                if c.revoked_at is None and secrets_compare(c.token_hash, token_hash)
            ),
            None,
        )
        if row is None:
            raise AuthenticationError("Invalid API key.", code="api_key_invalid")
        now = datetime.now(UTC)
        last = row.last_used_at
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if last is None or (now - last).total_seconds() > 60:
            row.last_used_at = now
        user_id = row.user_id
    return await auth_service.get_authenticated_user(user_id)


def secrets_compare(a: str, b: str) -> bool:
    return secrets.compare_digest(a, b)


async def get_current_user(
    request: Request,
    credentials: BearerDep,
    settings: SettingsDep,
    auth_service: AuthServiceDep,
    database: DatabaseDep,
    x_api_key: str | None = Header(default=None),
) -> User:
    if credentials is None:
        if x_api_key:
            user = await _user_from_api_key(x_api_key, database, auth_service)
            _set_actor(request, user)
            return user
        raise AuthenticationError("Missing bearer token.", code="missing_token")

    payload = decode_token(credentials.credentials, settings, TokenType.ACCESS)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Malformed token subject.", code="token_invalid") from exc

    issued_at = payload.get("iat")
    user = await auth_service.get_authenticated_user(
        user_id, token_issued_at=issued_at if isinstance(issued_at, int) else None
    )
    _set_actor(request, user)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    authorize(user, Permission.ADMIN_ACCESS)
    return user


AdminUser = Annotated[User, Depends(require_admin)]


async def require_sudo_admin(user: AdminUser) -> User:
    authorize(user, Permission.SUDO)
    return user


SudoAdminUser = Annotated[User, Depends(require_sudo_admin)]


async def require_write_admin(user: AdminUser) -> User:
    authorize(user, Permission.WRITE_USERS)
    return user


WriteAdminUser = Annotated[User, Depends(require_write_admin)]


async def enforce_agent_ingest_quota(
    node_id: uuid.UUID,
    agent: AgentServiceForQuota,
    settings: SettingsDep,
    cache: CacheDep,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
) -> None:
    await agent.authenticate(node_id, x_agent_token)
    await enforce_ingest_quota(cache, node_id, limit=settings.agent_ingest_rate_limit_per_minute)


AgentIngestQuota = Annotated[None, Depends(enforce_agent_ingest_quota)]
