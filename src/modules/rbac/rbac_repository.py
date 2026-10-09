from typing import Dict, List
from uuid import UUID

from db.db_session import get_async_db
from exceptions.app_exception import InternalServerException
from fastapi import Depends
from loguru import logger
from modules.authentication.auth_model import Permission, Role, RolePermission, UserRole
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class RBACRepository:
    """Repository for database operations related to Roles and Permissions."""

    def __init__(
        self, 
        db: AsyncSession = Depends(get_async_db)
    ):
        self.db = db

    async def get_user_roles_and_permissions(
        self, user_id: UUID
    ) -> Dict[str, any]:
        """
        Fetches all assigned role names and permission codes for a given user UUID.
        
        Flow:
        1. Fetch role names from auth.user_roles joined with auth.roles.
        2. Fetch permission codes from auth.user_roles -> auth.role_permissions -> auth.permissions.
        3. Returns structured dict: {"user_id": str(user_id), "roles": [...], "permissions": [...]}
        """
        try:
            # Fetch assigned role names
            role_stmt = (
                select(Role.name)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user_id)
            )
            role_res = await self.db.execute(role_stmt)
            roles: List[str] = [r[0] for r in role_res.fetchall()]

            # Fetch assigned permission codes
            perm_stmt = (
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(UserRole.user_id == user_id)
            )
            perm_res = await self.db.execute(perm_stmt)
            permissions: List[str] = list(set([p[0] for p in perm_res.fetchall()]))

            return {
                "user_id": str(user_id),
                "roles": roles,
                "permissions": permissions
            }
        except Exception as e:
            logger.error(f"Failed to query roles and permissions for user {user_id}: {e}")
            raise InternalServerException(
                message="Error querying user roles and permissions.",
                error_code="USER_ROLE_PERMISSION_FAILED"
            )

    async def get_user_role_permission(self, user_id: UUID) -> Dict[str, any]:
        """Backward compatibility wrapper for get_user_roles_and_permissions."""
        return await self.get_user_roles_and_permissions(user_id)
    