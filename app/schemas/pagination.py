from __future__ import annotations

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, description="1-indexed page number.")
    size: int = Field(default=20, ge=1, le=100, description="Items per page.")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size


class PageMeta(BaseModel):
    page: int
    size: int
    total: int
    pages: int


class Page[T](BaseModel):
    items: list[T]
    meta: PageMeta

    @classmethod
    def create(cls, items: list[T], total: int, params: PaginationParams) -> Page[T]:
        pages = (total + params.size - 1) // params.size if params.size else 0
        return cls(
            items=items,
            meta=PageMeta(page=params.page, size=params.size, total=total, pages=pages),
        )


class CursorParams(BaseModel):
    size: int = Field(default=20, ge=1, le=100, description="Items per page.")
    cursor: str | None = Field(default=None, description="Opaque pagination cursor.")

    @property
    def limit(self) -> int:
        return self.size


class CursorPage[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None
    size: int
