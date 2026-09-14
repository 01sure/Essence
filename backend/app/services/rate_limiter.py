"""
限流抽象：默认内存桶；配置 REDIS_URL 时自动切换到 Redis Lua 滑动窗口。
- 本地内存桶用于开发、单 worker 部署
- Redis Lua 用于多 worker / 多实例部署（简历面试重点）

Lua 脚本：使用有序集合 ZSET，保留 60s 窗口内的所有请求时间戳，
每次请求时清理过期、添加当前时间戳、返回窗口内的请求数，
应用层据此判断是否超过阈值——**保证跨进程限流准确**。
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_LUA_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local expire = window + 1
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count < limit then
    redis.call('ZADD', key, now, now .. '-' .. math.random(1000000))
    redis.call('EXPIRE', key, expire)
    return {1, count + 1}
end
return {0, count}
"""


class MemoryLimiter:
    def __init__(self, limit_per_min: int):
        self.limit = limit_per_min
        self._buckets: dict[str, deque] = defaultdict(deque)

    async def check(self, key: str) -> tuple[bool, int]:
        limit = self.limit
        now = time.time()
        if len(self._buckets) > 10000:
            stale = [k for k, v in self._buckets.items() if not v or now - v[-1] > 120]
            for k in stale:
                self._buckets.pop(k, None)
        bucket = self._buckets[key]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= limit:
            return False, len(bucket)
        bucket.append(now)
        return True, len(bucket)


class RedisLimiter:
    def __init__(self, limit_per_min: int, redis_url: str):
        import redis.asyncio as redis  # type: ignore

        self.limit = limit_per_min
        self._redis = redis.from_url(redis_url, decode_responses=False)
        self._sha = None

    async def _get_sha(self) -> str:
        if self._sha is None:
            self._sha = await self._redis.script_load(_LUA_SLIDING_WINDOW)
        return self._sha

    async def check(self, key: str) -> tuple[bool, int]:
        now = int(time.time() * 1000)
        sha = await self._get_sha()
        ok, cnt = await self._redis.evalsha(sha, 1, f"rl:{key}", now, 60_000, self.limit)
        return bool(ok), int(cnt)


_limiter: MemoryLimiter | RedisLimiter | None = None


def _make_limiter():
    s = get_settings()
    limit = s.RATE_LIMIT_PER_MIN
    url = (s.REDIS_URL or "").strip()
    if not url:
        logger.info("使用 内存滑动窗口 限流（单进程） limit=%s/min", limit)
        return MemoryLimiter(limit)
    try:
        lim = RedisLimiter(limit, url)
        logger.info("使用 Redis Lua 滑动窗口 限流（多进程/多实例） limit=%s/min url=%s", limit, url.split("@")[-1])
        return lim
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis 限流初始化失败，回退到内存桶：%s", exc)
        return MemoryLimiter(limit)


def get_limiter() -> MemoryLimiter | RedisLimiter:
    global _limiter
    if _limiter is None:
        _limiter = _make_limiter()
    return _limiter


async def rate_check(key: str) -> bool:
    lim = get_limiter()
    ok, _ = await lim.check(key)
    return ok
