from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from pydantic import Field

from app.core.exceptions import ConflictError, ValidationError
from app.core.logging import get_logger
from app.core.security import hash_password_async, validate_password_strength
from app.dependencies.core import CacheDep, SessionDep
from app.domain.user import User, UserRole
from app.schemas.base import APIModel, InputModel
from app.services import setup_service

router = APIRouter(prefix="/setup", tags=["setup"])
logger = get_logger("xlink.setup")


class SetupStatus(APIModel):
    needs_setup: bool


class SetupRequest(InputModel):
    token: str = Field(min_length=8, max_length=128)
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=256)


class SetupResult(APIModel):
    id: uuid.UUID
    username: str


@router.get("/status", response_model=SetupStatus)
async def setup_status(session: SessionDep) -> SetupStatus:
    return SetupStatus(needs_setup=await setup_service.needs_setup(session))


@router.post("", response_model=SetupResult, status_code=status.HTTP_201_CREATED)
async def run_setup(payload: SetupRequest, session: SessionDep, cache: CacheDep) -> SetupResult:
    if not await setup_service.needs_setup(session):
        raise ConflictError("Panel is already set up.", code="setup_done")
    try:
        validate_password_strength(payload.password)
    except ValueError as exc:
        raise ValidationError(str(exc), code="weak_password") from exc
    # Validate everything that can fail BEFORE consuming the token, so a typo
    # does not lock the operator out until the next restart.
    hashed = await hash_password_async(payload.password)
    if not await setup_service.consume_token(cache, payload.token):
        raise ValidationError("Invalid or expired setup token.", code="setup_token_invalid")
    admin = User(
        username=payload.username,
        hashed_password=hashed,
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
        is_sudo=True,
    )
    session.add(admin)
    try:
        await session.flush()
    except Exception:
        await setup_service.restore_token(cache, payload.token)
        raise
    logger.info("setup_completed", username=admin.username)
    return SetupResult(id=admin.id, username=admin.username)
