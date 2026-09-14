"""运行时设置缓存：读取 settings 表中的品牌人设/话术/规则，TTL 缓存"""
import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting

logger = logging.getLogger(__name__)

_TTL = 30  # 秒


class SettingsCache:
    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._loaded_at: float = 0.0

    async def _load(self, db: AsyncSession) -> None:
        rows = (await db.execute(select(Setting))).scalars().all()
        self._cache = {r.key: r.value for r in rows}
        self._loaded_at = time.time()

    async def get_all(self, db: AsyncSession) -> dict[str, Any]:
        if time.time() - self._loaded_at > _TTL:
            try:
                await self._load(db)
            except Exception:
                logger.exception("加载运行时设置失败")
        return self._cache

    async def get(self, db: AsyncSession, key: str, default: Any = None) -> Any:
        all_settings = await self.get_all(db)
        return all_settings.get(key, default)

    def invalidate(self) -> None:
        self._loaded_at = 0.0


settings_cache = SettingsCache()
