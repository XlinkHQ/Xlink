from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import TokenType, decode_token
from app.dependencies.core import SettingsDep
from app.dependencies.services import AuthServiceDep
from app.domain.user import User

_bearer = HTTPBearer(auto_error=False, description="JWT access token")
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


async def get_current_user(
    credentials: BearerDep,
    settings: SettingsDep,
    auth_service: AuthServiceDep,
) -> User:
    if credentials is None:
        raise AuthenticationError("Missing bearer token.", code="missing_token")

    payload = decode_token(credentials.credentials, settings, TokenType.ACCESS)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Malformed token subject.", code="token_invalid") from exc

    return await auth_service.get_authenticated_user(user_id)


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise PermissionDeniedError("Administrator access required.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
