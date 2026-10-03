from core.settings import settings
from db.cache_session import get_async_cache
from fastapi import Depends, Request
import redis.asyncio as aioredis
from loguru import logger

from exceptions.app_exception import TooManyRequestsException, UnauthorizedException


def rate_limit_by_ip(max_requests: int = 10, window_sec: int = 60):
    """Rate limit dependency that restricts client requests by IP address using Redis."""

    async def dependency(
        request: Request,
        redis: aioredis.Redis = Depends(get_async_cache)
    ):  
        # check client's sercet header value against server secret header for security
        secret_header = request.headers.get(settings.SECRET_HEADER_NAME, "xxx")

        if secret_header != settings.SECRET_HEADER_VALUE:
            logger.warning("Unidentified client trying to access resource.")
            raise UnauthorizedException(
                    message="Unauthorized requests not allowed.",
                    error_code="UNAUTHORIZED"
                )
        
        # Secure client IP resolution behind proxies (X-Forwarded-For)
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            # First IP in the list is the original client IP
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        # Unique key per request path and IP
        endpoint = request.scope["route"].path
        key = f"rate_limit:{endpoint}:{ip}"

        try:
            # Atomic increment request count
            current_requests = await redis.incr(key)

            # Set TTL on the first request in the window
            if current_requests == 1:
                await redis.expire(key, window_sec)

            # If request limit is exceeded, raise TooManyRequestsException
            if current_requests > max_requests:
                ttl = await redis.ttl(key)
                retry_after = ttl if ttl > 0 else window_sec
                raise TooManyRequestsException(
                    message="Too many requests. Please try again later.",
                    error_code="RATE_LIMIT_EXCEEDED",
                    details={"retryAfterSeconds": retry_after}
                )
        except TooManyRequestsException:
            raise
        except Exception as e:
            # Fallback gracefully if Redis is down or experiences connection drops
            logger.warning(f"Rate limiting checks bypassed due to Redis connection issue: {e}")

    return dependency
