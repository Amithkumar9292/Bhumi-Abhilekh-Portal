"""
Redis async client factory.
Used for caching, rate-limit state, and background job queues.
"""

import redis.asyncio as aioredis

from app.config import settings

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """
    Returns a Redis client.
    Works as a FastAPI dependency OR can be called directly in background tasks.
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
    return _redis_pool


async def get_redis_client() -> aioredis.Redis:
    """Direct client for use outside of request context (alias for get_redis)."""
    return await get_redis()


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
