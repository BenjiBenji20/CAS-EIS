import json
from typing import List, Sequence
from uuid import UUID
from fastapi import Depends
from loguru import logger

from exceptions.app_exception import BadRequestException, NotFoundException
from modules.authentication.auth_repository import AuthenticationRepository
from modules.rbac.rbac_repository import RBACRepository
from modules.rbac.rbac_schema import (
    BatchRolePermissionAssignmentPayload,
    BatchRolePermissionAssignmentResponse,
    ModuleSchema,
    RBACConfigResponse,
    RoleOverviewSchema,
    RolePermissionAssignmentResponse,
    UserPermissionsCachePayload,
    UserRBACSummaryResponse,
    UserRoleAssignmentResponse,
)
from shares.enums import (
    ROLE_DEFAULT_PERMISSIONS,
    RoleName,
    SystemPermission,
    build_rbac_hierarchy,
)
from utils.maintain_cache_key import MaintainCacheKeyUtils



class RBACService:
    """
    Service handling RBAC configuration resolution, Redis caching,
    scalable role/permission assignment, and cache invalidation.
    """

    def __init__(
        self,
        rbac_repo: RBACRepository = Depends(),
        auth_repo: AuthenticationRepository = Depends(),
        cache_utils: MaintainCacheKeyUtils = Depends()
    ):
        self.rbac_repo = rbac_repo
        self.auth_repo = auth_repo
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
        Must be called by Admin endpoints when updating roles or permissions.
        """
        await self.cache_utils.invalidate_user_permission_cache(str(user_id))


    async def get_rbac_configuration(self) -> RBACConfigResponse:
        """
        Returns unified RBAC configuration containing both:
        1. Hierarchical Module -> Resource -> Action tree directly from enums.py (source of truth).
        2. All active database roles with their granted permission codes and descriptions.
        """
        hierarchy_modules = build_rbac_hierarchy()
        roles_entities = await self.rbac_repo.get_all_roles()

        roles_overview = [
            RoleOverviewSchema(
                id=r.id,
                name=r.name,
                description=r.description,
                is_system_role=r.is_system_role,
                permissions=[p.code for p in r.permissions],
            )
            for r in roles_entities
        ]

        return RBACConfigResponse(
            modules=[ModuleSchema.model_validate(m) for m in hierarchy_modules],
            roles=roles_overview,
        )


    async def get_user_rbac_summary(self, user_id: UUID) -> UserRBACSummaryResponse:
        """Retrieves user's assigned roles and resolved effective permissions."""
        user = await self.auth_repo.get_by_id(user_id)
        if not user:
            logger.warning(f"User {user_id} not found when retrieving RBAC summary.")
            raise NotFoundException(message="User not found.", error_code="USER_NOT_FOUND")

        cached_payload = await self.get_or_cache_user_permissions(user_id)
        return UserRBACSummaryResponse(
            user_id=user.id,
            user_code=user.user_code,
            username=user.username,
            roles=cached_payload.roles,
            permissions=cached_payload.permissions,
        )


    async def assign_roles_to_user(
        self, user_id: UUID, role_identifiers: Sequence[str]
    ) -> UserRoleAssignmentResponse:
        """
        Replaces assigned roles for a given user and invalidates Redis cache.
        Accepts role names ('ADMIN', 'STAFF_USER') or role UUIDs.
        """
        user = await self.auth_repo.get_by_id(user_id)
        if not user:
            logger.warning(f"User {user_id} not found for role assignment.")
            raise NotFoundException(message="User not found.", error_code="USER_NOT_FOUND")

        # Resolve role identifiers to active Role entities
        matched_roles = await self.rbac_repo.resolve_roles(role_identifiers)
        if len(matched_roles) != len(role_identifiers):
            logger.warning(
                f"Invalid or inactive roles provided for user {user_id}: requested {role_identifiers}"
            )
            raise BadRequestException(
                message="One or more specified role names/IDs do not exist or are no longer active in enums.",
                error_code="INVALID_ROLE_ID"
            )

        role_ids = [r.id for r in matched_roles]
        assigned_role_names = await self.rbac_repo.assign_roles_to_user(user_id, role_ids)
        await self.rbac_repo.db.commit()

        # Invalidate user cache so updated permissions are immediately effective
        await self.invalidate_user_permissions(user_id)
        logger.info(f"Assigned roles {assigned_role_names} to user {user_id} and invalidated permission cache.")

        return UserRoleAssignmentResponse(
            status=True,
            message=f"Successfully updated roles for user {user.username}.",
            user_id=user_id,
            assigned_roles=assigned_role_names,
        )


    async def assign_permissions_to_role(
        self, role_identifier: str, permission_identifiers: Sequence[str]
    ) -> RolePermissionAssignmentResponse:
        """
        Replaces assigned permissions for a given role (by UUID or role name)
        and invalidates Redis caches for all users possessing this role.
        """
        role = await self.rbac_repo.get_role_by_identifier(role_identifier)
        if not role:
            logger.warning(f"Role '{role_identifier}' not found or inactive for permission assignment.")
            raise NotFoundException(
                message="Role not found or is no longer active in enums.",
                error_code="ROLE_NOT_FOUND"
            )

        # Resolve permission codes or UUIDs
        matched_perms = []
        if permission_identifiers:
            matched_perms = await self.rbac_repo.resolve_permissions(permission_identifiers)
            if len(matched_perms) != len(permission_identifiers):
                logger.warning(
                    f"Invalid or inactive permissions provided for role '{role.name}': requested {permission_identifiers}"
                )
                raise BadRequestException(
                    message="One or more specified permission codes/IDs do not exist or are no longer active in enums.",
                    error_code="INVALID_PERMISSION_ID"
                )

        perm_ids = [p.id for p in matched_perms]
        assigned_perm_codes = await self.rbac_repo.assign_permissions_to_role(
            role.id, perm_ids
        )

        await self.rbac_repo.db.commit()

        # Invalidate cache for all users holding this role
        affected_user_ids = await self.rbac_repo.get_user_ids_by_role(role.id)
        for u_id in affected_user_ids:
            await self.invalidate_user_permissions(u_id)

        logger.info(f"Updated permissions for role '{role.name}' and invalidated cache for {len(affected_user_ids)} users.")

        return RolePermissionAssignmentResponse(
            status=True,
            message=f"Successfully updated permissions for role '{role.name}'.",
            role_id=role.id,
            role_name=role.name,
            assigned_permissions=assigned_perm_codes,
        )


    async def batch_assign_role_permissions(
        self, payload: BatchRolePermissionAssignmentPayload
    ) -> BatchRolePermissionAssignmentResponse:
        """
        Atomically updates permissions across multiple roles in a single operation.
        Invalidates Redis caches for all affected users across all updated roles.
        """
        updated_role_names: List[str] = []
        all_affected_user_ids: set[UUID] = set()

        for item in payload.assignments:
            role = await self.rbac_repo.get_role_by_identifier(item.role)
            if not role:
                raise NotFoundException(
                    message=f"Role '{item.role}' not found or inactive.",
                    error_code="ROLE_NOT_FOUND"
                )

            matched_perms = []
            if item.permissions:
                matched_perms = await self.rbac_repo.resolve_permissions(item.permissions)
                if len(matched_perms) != len(item.permissions):
                    raise BadRequestException(
                        message=f"One or more permission codes for role '{item.role}' do not exist or are inactive.",
                        error_code="INVALID_PERMISSION_ID"
                    )

            perm_ids = [p.id for p in matched_perms]
            await self.rbac_repo.assign_permissions_to_role(role.id, perm_ids)
            updated_role_names.append(role.name)

            affected_users = await self.rbac_repo.get_user_ids_by_role(role.id)
            all_affected_user_ids.update(affected_users)

        await self.rbac_repo.db.commit()

        for u_id in all_affected_user_ids:
            await self.invalidate_user_permissions(u_id)

        logger.info(f"Batch assigned permissions for roles: {updated_role_names}. Invalidated {len(all_affected_user_ids)} user caches.")

        return BatchRolePermissionAssignmentResponse(
            status=True,
            message=f"Successfully batch updated permissions for {len(updated_role_names)} roles.",
            updated_roles=updated_role_names,
        )


    async def reset_role_to_defaults(
        self, role_identifier: str
    ) -> RolePermissionAssignmentResponse:
        """
        Resets a role's permissions back to its code-defined ROLE_DEFAULT_PERMISSIONS preset.
        """
        role = await self.rbac_repo.get_role_by_identifier(role_identifier)
        if not role:
            raise NotFoundException(
                message=f"Role '{role_identifier}' not found.",
                error_code="ROLE_NOT_FOUND"
            )

        try:
            r_enum = RoleName(role.name)
        except ValueError:
            raise BadRequestException(
                message=f"Role '{role.name}' is not a defined system role enum.",
                error_code="ROLE_NOT_FOUND"
            )

        default_perms = ROLE_DEFAULT_PERMISSIONS.get(r_enum, set())
        perm_codes = [p.value for p in default_perms]
        return await self.assign_permissions_to_role(role.name, perm_codes)


    async def sync_enums_to_db(self) -> dict:
        """Invokes idempotent synchronization of enums with database tables."""
        return await self.rbac_repo.sync_enums_to_db()
