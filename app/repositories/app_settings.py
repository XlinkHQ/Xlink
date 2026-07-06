from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.app_settings import SINGLETON_ID, AppSettings


class AppSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self) -> AppSettings:
        row = await self.session.get(AppSettings, SINGLETON_ID)
        if row is None:
            row = AppSettings(id=SINGLETON_ID)
            self.session.add(row)
            await self.session.flush()
        return row
