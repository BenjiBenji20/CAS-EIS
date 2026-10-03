from typing import AsyncGenerator
import redis.asyncio as aioredis
from clients.redis import redis_async_client


async def get_async_cache() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency for accessing the singleton async Redis cache instance."""
    yield redis_async_client.redis
