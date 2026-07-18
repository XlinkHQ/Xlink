from __future__ import annotations

from fastapi import APIRouter, status

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import hash_password_async, verify_password_async
from app.dependencies.auth import CurrentUser
from app.dependencies.core import SettingsDep
from app.dependencies.services import AuthServiceDep, TokenServiceDep, UserTotpServiceDep
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    TotpConfirmRequest,
    TotpEnrollRequest,
    TotpEnrollResponse,
)
from app.schemas.user import UserCreate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, auth: AuthServiceDep, settings: SettingsDep) -> AuthResponse:
    if not settings.registration_enabled:
        raise PermissionDeniedError(
            "Self-service registration is disabled.", code="registration_disabled"
        )
    return await auth.register(payload)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, auth: AuthServiceDep) -> AuthResponse:
    return await auth.login(payload.identifier, payload.password, payload.totp_code)


@router.post("/2fa/enroll", response_model=TotpEnrollResponse)
async def totp_enroll(
    user: CurrentUser, auth: AuthServiceDep, payload: TotpEnrollRequest | None = None
) -> TotpEnrollResponse:
    secret, uri = await auth.begin_totp_enrollment(
        user.id, code=payload.code if payload else None
    )
    return TotpEnrollResponse(secret=secret, otpauth_uri=uri)


@router.post("/2fa/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def totp_confirm(
    payload: TotpConfirmRequest, user: CurrentUser, auth: AuthServiceDep
) -> None:
    await auth.confirm_totp(user.id, payload.code)


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def totp_disable(
    payload: TotpConfirmRequest, user: CurrentUser, auth: AuthServiceDep
) -> None:
    await auth.disable_totp(user.id, payload.code)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, auth: AuthServiceDep) -> TokenPair:
    return await auth.refresh(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, auth: AuthServiceDep) -> None:

    await auth.logout(payload.refresh_token)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(user: CurrentUser, auth: AuthServiceDep) -> None:
    await auth.logout_everywhere(user.id)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser,
    users: UserTotpServiceDep,
    tokens: TokenServiceDep,
) -> None:
    if not user.hashed_password or not await verify_password_async(
        payload.current_password, user.hashed_password
    ):
        raise AuthenticationError("Current password is incorrect.", code="invalid_credentials")
    new_hash = await hash_password_async(payload.new_password)
    await users.update_password_hash(user, new_hash)
    await tokens.revoke_all(user.id)
