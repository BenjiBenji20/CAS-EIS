import json
from uuid import UUID
from fastapi import Depends
from loguru import logger

from modules.rbac.rbac_repository import RBACRepository
from modules.rbac.rbac_schema import UserPermissionsCachePayload
from utils.maintain_cache_key import MaintainCacheKeyUtils


class RBACService:
    """
    Service handling RBAC resolution, Redis caching, and cache invalidation.
    
    Caching Pattern:
    - Key Generator: MaintainCacheKeyUtils.create_user_permission_cache_key(user_id) -> 'user_permission:{user_id}'
    - Set Location: RBACService.get_or_cache_user_permissions() (on cache miss)
    - Read Location: dependencies/rbac_guard.py -> require_permission(), require_role(), require_any_permission()
    - Invalidate Location: RBACService.invalidate_user_permissions() (on Superadmin role/permission mutation)
    """

    def __init__(
        self,
        rbac_repo: RBACRepository = Depends(),
        cache_utils: MaintainCacheKeyUtils = Depends()
    ):
        self.rbac_repo = rbac_repo
        self.cache_utils = cache_utils

    async def get_or_cache_user_permissions(self, user_id: UUID) -> UserPermissionsCachePayload:
        """
        Retrieves user roles and permissions from Redis cache (~0.5ms).
        On cache miss, queries PostgreSQL DB via RBACRepository, warms Redis cache, and returns payload.
        """
        user_id_str = str(user_id)
        key = self.cache_utils.create_user_permission_cache_key(user_id_str)
        
        # Try Redis Cache Hit (O(1) ~0.5ms Read)
        try:
            cached_raw = await self.cache_utils.async_cache.get(key)
            if cached_raw is not None:
                data = json.loads(cached_raw) if isinstance(cached_raw, (str, bytes)) else cached_raw
                return UserPermissionsCachePayload(
                    user_id=UUID(str(data.get("user_id", user_id))),
                    roles=data.get("roles", []),
                    permissions=data.get("permissions", [])
                )
        except Exception as e:
            logger.warning(f"Error reading user permissions from Redis for user {user_id}: {e}")

        # Redis Cache Miss: Fallback to PostgreSQL DB
        logger.info(f"Redis cache miss for user_permission:{user_id}. Querying PostgreSQL DB...")
        db_payload = await self.rbac_repo.get_user_roles_and_permissions(user_id)
        
        # Populate Redis Cache
        await self.cache_utils.cache_user_permissions(user_id_str, db_payload)

        return UserPermissionsCachePayload(
            user_id=user_id,
            roles=db_payload.get("roles", []),
            permissions=db_payload.get("permissions", [])
        )

    async def invalidate_user_permissions(self, user_id: UUID) -> None:
        """
        Invalidates cached permissions for a user in Redis.
        Must be called by Superadmin endpoints when updating roles or permissions.
        """
        await self.cache_utils.invalidate_user_permission_cache(str(user_id))
