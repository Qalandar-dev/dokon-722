"""Fixed-window rate limiting in Redis."""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.exceptions import RateLimitError


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> None:
        """Count one attempt; raise ``RateLimitError`` once ``limit`` is exceeded."""
        full_key = f"rl:{key}"
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(full_key)
            pipe.expire(full_key, window_seconds, nx=True)
            count, _ = await pipe.execute()
        if int(count) > limit:
            ttl = await self.redis.ttl(full_key)
            raise RateLimitError(details={"retry_after_seconds": max(int(ttl), 1)})

    async def reset(self, key: str) -> None:
        await self.redis.delete(f"rl:{key}")
