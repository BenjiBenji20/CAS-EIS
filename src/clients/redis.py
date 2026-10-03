import redis.asyncio as aioredis
from core.settings import settings


class RedisClient:
    def __init__(self):
        self.pool: aioredis.ConnectionPool | None = None
        self._redis: aioredis.Redis | None = None

    def _init_pool(self) -> None:
        if self.pool is None:
            if not settings.REDIS_URL:
                raise ValueError("REDIS_URL is not configured in settings.")
            self.pool = aioredis.ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=20,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
            self._redis = aioredis.Redis(connection_pool=self.pool)

    @property
    def redis(self) -> aioredis.Redis:
        """Lazy getter for the singleton Redis client instance."""
        self._init_pool()
        return self._redis

    async def ping(self) -> bool:
        """Health check endpoint."""
        return await self.redis.ping()

    async def close(self) -> None:
        """Gracefully close the connection pool on application shutdown."""
        if self._redis is not None:
            await self._redis.aclose()
        if self.pool is not None:
            await self.pool.aclose()
        self._redis = None
        self.pool = None


redis_async_client = RedisClient()
