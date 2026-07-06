from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.cli.runner import run_cli
from app.dependencies.auth import SudoAdminUser
from app.dependencies.core import CacheDep, SessionDep, SettingsDep

router = APIRouter(prefix="/cli", tags=["cli"])


class CliCommand(BaseModel):
    command: str


class CliResult(BaseModel):
    output: str


@router.post("", response_model=CliResult)
async def run_command(
    payload: CliCommand,
    _admin: SudoAdminUser,
    session: SessionDep,
    cache: CacheDep,
    settings: SettingsDep,
) -> CliResult:
    return CliResult(output=await run_cli(session, cache, settings, payload.command))
