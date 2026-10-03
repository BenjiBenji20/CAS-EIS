from loguru import logger
from fastapi import Depends
import redis.asyncio as aioredis

from db.cache_session import get_async_cache
from core.settings import settings

class MaintainCacheKeyUtils:
    
    def __init__(self, async_cache: aioredis.Redis = Depends(get_async_cache)):
        self.async_cache = async_cache

    async def profile_completion_cache(self, user_id: str, is_profile_completed: bool):
        """
        Implementation References:
        - dependencies/current_user/require_completed_profile()
        - modules/authentication/auth_service/AuthenticationService
        """
        # Cache dedicated profile completion flag for lightweight dependency checks
        profile_cache_key = self.get_profile_completion_key(user_id)
        try:
            await self.async_cache.set(
                name=profile_cache_key,
                value="1" if is_profile_completed else "0",
                ex=settings.REFRESH_JWT_EXPIRY_SEC
            )
        except Exception as e:
            logger.warning(f"Failed to cache profile completion status in Redis: {e}")

    def get_profile_completion_key(self, user_id: str) -> str:
        return f"user:profile_completed:{user_id}"


    async def record_failed_login(
        self, ip: str, username: str, window_sec: int = 900, max_attempts: int = 5
    ) -> bool:
        """
        Record a failed login attempt for (IP, Username) pair in Redis.
        Returns True if threshold reached and lockout key was created.
        """
        count_key = self.get_failed_login_count_key(ip, username)
        block_key = self.get_failed_login_block_key(ip, username)
        try:
            current_attempts = await self.async_cache.incr(count_key)
            if current_attempts == 1:
                await self.async_cache.expire(count_key, window_sec)

            if current_attempts >= max_attempts:
                await self.async_cache.set(name=block_key, value="1", ex=window_sec)
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to record failed login attempt in Redis: {e}")
            return False

    async def clear_failed_login(self, ip: str, username: str):
        """Clear failed attempt counter and lockout block keys on successful login."""
        count_key = self.get_failed_login_count_key(ip, username)
        block_key = self.get_failed_login_block_key(ip, username)
        try:
            await self.async_cache.delete(count_key, block_key)
        except Exception as e:
            logger.warning(f"Failed to clear failed login state in Redis: {e}")
            
    def get_failed_login_count_key(self, ip: str, username: str) -> str:
        return f"failed_login_count:{ip}:{username}"

    def get_failed_login_block_key(self, ip: str, username: str) -> str:
        return f"failed_login_block:{ip}:{username}"

    def create_cache_key(self, session_id: str, user_id: str) -> str:
        return f"sessions:{session_id}:user:{user_id}"
    
    def create_cache_name(self, user_id: str) -> str:
        return f"user:sessions:{user_id}"

    async def is_ip_user_blocked(self, ip: str, username: str) -> bool:
        """Check if specific (IP, Username) pair is currently locked out in Redis."""
        block_key = self.get_failed_login_block_key(ip, username)
        try:
            return bool(await self.async_cache.exists(block_key))
        except Exception as e:
            logger.warning(f"Failed to check IP/Username lockout status in Redis: {e}")
            return False
        
    async def admin_unblock_user(self, username: str):
        # Search for any active IP block keys for this username in Redis
        async for key in self.async_cache.scan_iter(f"failed_login_block:*:{username}"):
            await self.async_cache.delete(key)
        async for key in self.async_cache.scan_iter(f"failed_login_count:*:{username}"):
            await self.async_cache.delete(key)
