from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base


class BaseRepository[ModelT: Base]:
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id_: Any) -> ModelT | None:
        return await self.session.get(self.model, id_)

    async def get_by(self, **filters: Any) -> ModelT | None:
        result = await self.session.execute(self._select().filter_by(**filters).limit(1))
        return result.scalar_one_or_none()

    async def exists(self, **filters: Any) -> bool:
        stmt = select(func.count()).select_from(self.model).filter_by(**filters)
        return bool(await self.session.scalar(stmt))

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        order_by: Any | None = None,
        **filters: Any,
    ) -> Sequence[ModelT]:
        stmt = self._select().filter_by(**filters).offset(offset).limit(limit)
        stmt = stmt.order_by(order_by if order_by is not None else self.model.id.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self, **filters: Any) -> int:
        stmt = select(func.count()).select_from(self.model).filter_by(**filters)
        return int(await self.session.scalar(stmt) or 0)

    async def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)

        await self.session.flush()
        return instance

    async def add_all(self, instances: Sequence[ModelT]) -> Sequence[ModelT]:
        self.session.add_all(instances)
        await self.session.flush()
        return instances

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
        await self.session.flush()

    async def delete_where(self, **filters: Any) -> int:
        result = await self.session.execute(delete(self.model).filter_by(**filters))
        return result.rowcount or 0

    def _select(self) -> Select[tuple[ModelT]]:
        return select(self.model)
