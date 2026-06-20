from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config_entry import ConfigEntry


class ConfigRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all(self) -> dict[str, Any]:
        result = await self.db.execute(select(ConfigEntry))
        entries = result.scalars().all()
        return {row.key: row.value for row in entries}

    async def get(self, key: str) -> Any:
        result = await self.db.execute(
            select(ConfigEntry).where(ConfigEntry.key == key)
        )
        entry = result.scalar_one_or_none()
        return entry.value if entry else None

    async def set(self, key: str, value: Any) -> None:
        stmt = (
            insert(ConfigEntry)
            .values(key=key, value=value)
            .on_conflict_do_update(
                index_elements=["key"],
                set_={"value": value, "updated_at": func.now()},
            )
        )
        await self.db.execute(stmt)

    async def set_many(self, entries: dict[str, Any]) -> None:
        for key, value in entries.items():
            await self.set(key, value)

    async def delete(self, key: str) -> None:
        await self.db.execute(delete(ConfigEntry).where(ConfigEntry.key == key))
