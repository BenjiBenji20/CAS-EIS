from typing import List
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import Depends
from loguru import logger

from db.cache_session import get_async_cache
from exceptions.app_exception import BadRequestException, NotFoundException
from modules.session.session_repo import UserSessionRepository
from modules.session.session_schema import (
    AdminUserSessionListItemResponse,
    SessionLogoutResponse,
    SessionUserInfo,
)
from utils.maintain_cache_key import MaintainCacheKeyUtils


class SessionService:
    """Service handling session lifecycle, revocation, and administrative overrides."""

    def __init__(
        self,
        user_session_repo: UserSessionRepository = Depends(),
        async_cache: aioredis.Redis = Depends(get_async_cache),
        cache_utils: MaintainCacheKeyUtils = Depends(),
    ):
        self.user_session_repo = user_session_repo
        self.async_cache = async_cache
        self.cache_utils = cache_utils


    async def logout_own_session(
        self, user_id: UUID, session_id: UUID
    ) -> SessionLogoutResponse:
        """
        Gracefully invalidates the caller's own active session in PostgreSQL and Redis.
        """
        logger.info(f"Logging out session {session_id} for user {user_id}")
        await self.user_session_repo.deactivate_session_by_id(session_id)

        # Invalidate Redis cache
        cache_key = self.cache_utils.create_cache_key(
            session_id=str(session_id), user_id=str(user_id)
        )
        cache_name = self.cache_utils.create_cache_name(user_id=str(user_id))
        try:
            await self.async_cache.delete(cache_key)
            await self.async_cache.srem(cache_name, cache_key)
        except Exception as e:
            logger.warning(f"Error purging session key from Redis: {e}")

        return SessionLogoutResponse(
            status=True,
            description="Successfully logged out of current session.",
            session_id=session_id,
        )


    async def admin_force_logout_by_session_id(
        self, session_id: UUID
    ) -> SessionLogoutResponse:
        """
        Administrator force-revocation of a specific session by its UUID.
        Immediate 401 on target terminal on subsequent request.
        """
        logger.info(f"Admin force-revoking session {session_id}")
        session = await self.user_session_repo.get_by_id(session_id)
        if not session:
            logger.warning(f"Session {session_id} not found.")
            raise NotFoundException(message="Session not found.")

        if not session.is_active:
            raise BadRequestException(message="Session is already inactive.")

        await self.user_session_repo.deactivate_session_by_id(session_id)

        # Evict from Redis
        cache_key = self.cache_utils.create_cache_key(
            session_id=str(session.id), user_id=str(session.user_id)
        )
        cache_name = self.cache_utils.create_cache_name(user_id=str(session.user_id))
        try:
            await self.async_cache.delete(cache_key)
            await self.async_cache.srem(cache_name, cache_key)
        except Exception as e:
            logger.warning(f"Error purging session key from Redis: {e}")

        return SessionLogoutResponse(
            status=True,
            description=f"Session {session_id} has been forcefully revoked.",
            session_id=session_id,
        )

    async def admin_force_logout_all_sessions(
        self,
        target_user_id: UUID,
    ) -> SessionLogoutResponse:
        """
        Administrator mass termination of all active sessions for a target user.
        Step-up administrative credential verification is guarded at the route level via require_sudo_credential.
        """
        logger.info(f"Executing mass session revocation for user {target_user_id}")
        # 1. Bulk deactivate in PostgreSQL
        revoked_count = await self.user_session_repo.deactivate_all_active_by_user_id(
            target_user_id
        )

        # 2. Purge all Redis session keys for user
        cache_name = self.cache_utils.create_cache_name(user_id=str(target_user_id))
        try:
            active_keys = await self.async_cache.smembers(cache_name)
            if active_keys:
                for key in active_keys:
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else str(key)
                    await self.async_cache.delete(key_str)
            await self.async_cache.delete(cache_name)
        except Exception as e:
            logger.warning(f"Error purging all sessions from Redis for user {target_user_id}: {e}")

        return SessionLogoutResponse(
            status=True,
            description=f"All active sessions for user {target_user_id} terminated ({revoked_count} sessions revoked).",
            revoked_count=revoked_count,
        )


    async def get_all_active_sessions(
        self,
    ) -> List[AdminUserSessionListItemResponse]:
        """Query all currently active sessions across all users with joined identity and profile data."""
        sessions = await self.user_session_repo.get_all_active_sessions_with_user_info()
        items = []
        for s in sessions:
            u = getattr(s, "user", None)
            full_name = None
            if u and getattr(u, "profile", None):
                first = u.profile.first_name or ""
                last = u.profile.last_name or ""
                full_name = f"{first} {last}".strip() or None

            roles = [r.name for r in u.roles] if u and getattr(u, "roles", None) else []
            user_status = str(u.status.value) if u and hasattr(u.status, "value") else str(u.status) if u else "UNKNOWN"

            user_info = SessionUserInfo(
                user_id=s.user_id,
                user_code=u.user_code if u and getattr(u, "user_code", None) else "UNKNOWN",
                username=u.username if u else "unknown",
                email=u.email if u else "unknown",
                status=user_status,
                roles=roles,
                full_name=full_name,
            )

            items.append(
                AdminUserSessionListItemResponse(
                    id=s.id,
                    user_id=s.user_id,
                    is_active=s.is_active,
                    ip_address=s.ip_address,
                    user_agent=s.user_agent,
                    expires_at=s.expires_at,
                    last_active_at=s.last_active_at,
                    created_at=s.created_at,
                    user=user_info,
                )
            )
        return items
