from __future__ import annotations

from fastapi import APIRouter, status

from app.dependencies.auth import CurrentUser
from app.dependencies.services import AuthServiceDep
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
)
from app.schemas.user import UserCreate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, auth: AuthServiceDep) -> AuthResponse:
    return await auth.register(payload)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, auth: AuthServiceDep) -> AuthResponse:
    return await auth.login(payload.identifier, payload.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, auth: AuthServiceDep) -> TokenPair:
    return await auth.refresh(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, auth: AuthServiceDep) -> None:
    await auth.logout(payload.refresh_token)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(user: CurrentUser, auth: AuthServiceDep) -> None:
    await auth.logout_everywhere(user.id)
