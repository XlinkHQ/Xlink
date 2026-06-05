from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.lifespan import AppState
from app.db.redis import RedisCache
from app.db.session import Database
from app.events.bus import EventBus
from app.providers.base.registry import ProviderRegistry


def get_state(request: Request) -> AppState:
    return request.app.state.xlink


def get_settings_dep(state: Annotated[AppState, Depends(get_state)]) -> Settings:
    return state.settings


def get_cache(state: Annotated[AppState, Depends(get_state)]) -> RedisCache:
    return state.cache


def get_providers(state: Annotated[AppState, Depends(get_state)]) -> ProviderRegistry:
    return state.providers


def get_events(state: Annotated[AppState, Depends(get_state)]) -> EventBus:
    return state.events


def get_database(state: Annotated[AppState, Depends(get_state)]) -> Database:
    return state.db


async def get_session(
    state: Annotated[AppState, Depends(get_state)],
) -> AsyncIterator[AsyncSession]:
    async with state.db.session() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
CacheDep = Annotated[RedisCache, Depends(get_cache)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
ProvidersDep = Annotated[ProviderRegistry, Depends(get_providers)]
EventsDep = Annotated[EventBus, Depends(get_events)]
DatabaseDep = Annotated[Database, Depends(get_database)]
