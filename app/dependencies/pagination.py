from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query

from app.dependencies.core import SettingsDep
from app.schemas.pagination import CursorParams, PaginationParams


def get_pagination(
    settings: SettingsDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int | None, Query(ge=1)] = None,
) -> PaginationParams:
    effective = size or settings.default_page_size

    effective = min(effective, settings.max_page_size)
    return PaginationParams(page=page, size=effective)


def get_cursor_pagination(
    settings: SettingsDep,
    size: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query()] = None,
) -> CursorParams:
    effective = size or settings.default_page_size
    effective = min(effective, settings.max_page_size)
    return CursorParams(size=effective, cursor=cursor)


def get_list_pagination(
    settings: SettingsDep,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query()] = None,
) -> PaginationParams | CursorParams:
    effective = size or settings.default_page_size
    effective = min(effective, settings.max_page_size)
    if page is not None:
        return PaginationParams(page=page, size=effective)
    return CursorParams(size=effective, cursor=cursor)


PaginationDep = Annotated[PaginationParams, Depends(get_pagination)]
CursorPaginationDep = Annotated[CursorParams, Depends(get_cursor_pagination)]
ListPaginationDep = Annotated[PaginationParams | CursorParams, Depends(get_list_pagination)]
