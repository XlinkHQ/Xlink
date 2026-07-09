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


def get_dispatcher(state: Annotated[AppState, Depends(get_state)]):
    # Shared, lifespan-owned dispatcher — its fire-and-forget webhook tasks are
    # drained on shutdown. Building one per request orphaned those tasks.
    return state.dispatcher


async def get_session(
    state: Annotated[AppState, Depends(get_state)],
) -> AsyncIterator[AsyncSession]:
    async with state.db.session() as session:
        yield session


async def get_reader_session(
    state: Annotated[AppState, Depends(get_state)],
) -> AsyncIterator[AsyncSession]:
    # Read-only session for replica-safe analytics/subscription reads. Falls back
    # to the primary when no replica is configured (see Database.reader_session).
    async with state.db.reader_session() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
CacheDep = Annotated[RedisCache, Depends(get_cache)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
# Replica-backed read session (falls back to the primary when no replica is
# configured). Only wire this into clearly read-only analytics/subscription reads.
ReaderSessionDep = Annotated[AsyncSession, Depends(get_reader_session)]
ProvidersDep = Annotated[ProviderRegistry, Depends(get_providers)]
EventsDep = Annotated[EventBus, Depends(get_events)]
DatabaseDep = Annotated[Database, Depends(get_database)]
DispatcherDep = Annotated[object, Depends(get_dispatcher)]
