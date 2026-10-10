from datetime import datetime, timezone
import json
from typing import List, Optional, Sequence
from uuid import UUID
from fastapi import Depends
from loguru import logger

from exceptions.app_exception import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from modules.authentication.auth_model import RBACChangeRequest, RBACChangeRequestStatus
from modules.authentication.auth_repository import AuthenticationRepository
from modules.rbac.rbac_repository import RBACRepository
from modules.rbac.rbac_schema import (
    AssignRolePermissionsPayload,
    AssignUserDirectPermissionsPayload,
    AssignUserRolesPayload,
    BatchRolePermissionAssignmentPayload,
    BatchRolePermissionAssignmentResponse,
    ModuleSchema,
    RBACChangeRequestResponse,
    RBACConfigResponse,
    ReviewChangeRequestPayload,
    RoleOverviewSchema,
    RolePermissionAssignmentResponse,
    UserDirectPermissionsResponse,
    UserPermissionsCachePayload,
    UserRBACSummaryResponse,
    UserRoleAssignmentResponse,
)
from modules.session.session_repo import UserSessionRepository
from shares.enums import (
    ROLE_DEFAULT_PERMISSIONS,
    ROLE_RANKS,
    RoleName,
    SystemPermission,
    build_rbac_hierarchy,
    get_role_rank,
    get_user_highest_rank,
)
from utils.maintain_cache_key import MaintainCacheKeyUtils


class RBACService:
    """
    Service handling RBAC configuration resolution, Redis caching,
    governance refusal rules, hierarchical dual-control change requests,
    and immediate cache/session revocation.
    """

    def __init__(
        self,
        rbac_repo: RBACRepository = Depends(),
        auth_repo: AuthenticationRepository = Depends(),
        session_repo: UserSessionRepository = Depends(),
        cache_utils: MaintainCacheKeyUtils = Depends(),
    ):
        self.rbac_repo = rbac_repo
        self.auth_repo = auth_repo
        self.session_repo = session_repo
        self.cache_utils = cache_utils

    async def get_or_cache_user_permissions(self, user_id: UUID) -> UserPermissionsCachePayload:
        """
        Retrieves user roles and permissions from Redis cache (~0.5ms).
        On cache miss, queries PostgreSQL DB via RBACRepository, warms Redis cache, and returns payload.
        """
        user_id_str = str(user_id)
        key = self.cache_utils.create_user_permission_cache_key(user_id_str)

        try:
            cached_raw = await self.cache_utils.async_cache.get(key)
            if cached_raw is not None:
                data = json.loads(cached_raw) if isinstance(cached_raw, (str, bytes)) else cached_raw
                return UserPermissionsCachePayload(
                    user_id=UUID(str(data.get("user_id", user_id))),
                    roles=data.get("roles", []),
                    permissions=data.get("permissions", []),
                )
        except Exception as e:
            logger.warning(f"Error reading user permissions from Redis for user {user_id}: {e}")

        logger.info(f"Redis cache miss for user_permission:{user_id}. Querying PostgreSQL DB...")
        db_payload = await self.rbac_repo.get_user_roles_and_permissions(user_id)

        await self.cache_utils.cache_user_permissions(user_id_str, db_payload)

        return UserPermissionsCachePayload(
            user_id=user_id,
            roles=db_payload.get("roles", []),
            permissions=db_payload.get("permissions", []),
        )

    async def invalidate_user_permissions(self, user_id: UUID) -> None:
        """
        Invalidates cached permissions for a user in Redis.
        Must be called post-commit when mutating roles or direct permissions.
        """
        await self.cache_utils.invalidate_user_permission_cache(str(user_id))

    async def get_rbac_configuration(self) -> RBACConfigResponse:
        """
        Returns unified RBAC configuration containing both:
        1. Hierarchical Module -> Resource -> Action tree directly from enums.py (source of truth).
        2. All active database roles with their ranks and granted permission codes.
        """
        hierarchy_modules = build_rbac_hierarchy()
        roles_entities = await self.rbac_repo.get_all_roles()

        roles_overview = [
            RoleOverviewSchema(
                id=r.id,
                name=r.name,
                rank=get_role_rank(r.name),
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
        """Retrieves user's assigned roles, direct grants, explicit denials, and effective permissions."""
        user = await self.auth_repo.get_by_id(user_id)
        if not user:
            logger.warning(f"User {user_id} not found when retrieving RBAC summary.")
            raise NotFoundException(message="User not found.", error_code="USER_NOT_FOUND")

        db_payload = await self.rbac_repo.get_user_roles_and_permissions(user_id)
        highest_rank = get_user_highest_rank(db_payload.get("roles", []))

        return UserRBACSummaryResponse(
            user_id=user.id,
            user_code=user.user_code,
            username=user.username,
            highest_rank=highest_rank,
            roles=db_payload.get("roles", []),
            direct_grants=db_payload.get("direct_grants", []),
            direct_revocations=db_payload.get("direct_revocations", []),
            permissions=db_payload.get("permissions", []),
        )

    async def assign_roles_to_user(
        self,
        operator_id: UUID,
        user_id: UUID,
        role_identifiers: Sequence[str],
        reason: str,
    ) -> UserRoleAssignmentResponse:
        """
        Assigns or updates roles for a target user with strict governance refusals:
        1. Operators cannot modify their own roles (self-mutation refused).
        2. Operators cannot modify users with equal or higher rank.
        3. Operators cannot assign roles with rank equal to or exceeding their own rank.
        4. Cannot demote the last remaining active Super Admin.
        5. Dual-authorization: Privilege elevations by non-super-admins create pending change requests.
        6. Immediate session revocation on demotion.
        """
        # Refusal 1: Self-mutation prevention
        if operator_id == user_id:
            logger.warning(f"Operator {operator_id} attempted self-mutation of roles.")
            raise ForbiddenException(
                message="Operators cannot modify their own assigned roles.",
                error_code="CANNOT_MODIFY_OWN_ROLES",
            )

        # Retrieve operator context
        operator_payload = await self.get_or_cache_user_permissions(operator_id)
        operator_rank = get_user_highest_rank(operator_payload.roles)

        # Retrieve target user context
        target_user = await self.auth_repo.get_by_id(user_id)
        if not target_user:
            logger.warning(f"User {user_id} not found for role assignment.")
            raise NotFoundException(message="User not found.", error_code="USER_NOT_FOUND")

        target_payload = await self.get_or_cache_user_permissions(user_id)
        target_current_rank = get_user_highest_rank(target_payload.roles)

        # Refusal 2: Hierarchy boundary (target user rank vs operator rank)
        if operator_rank < 100 and target_current_rank >= operator_rank:
            logger.warning(
                f"Operator {operator_id} (rank {operator_rank}) attempted to modify target {user_id} (rank {target_current_rank})."
            )
            raise ForbiddenException(
                message="Cannot modify roles for users with equal or higher rank.",
                error_code="INSUFFICIENT_ROLE_RANK",
            )

        # Resolve role identifiers
        matched_roles = await self.rbac_repo.resolve_roles(role_identifiers)
        if len(matched_roles) != len(role_identifiers):
            logger.warning(
                f"Invalid or inactive roles provided for user {user_id}: requested {role_identifiers}"
            )
            raise BadRequestException(
                message="One or more specified role names/IDs do not exist or are no longer active in enums.",
                error_code="INVALID_ROLE_ID",
            )

        # Refusal 3: Operator assigning role at or above own rank
        for r in matched_roles:
            r_rank = get_role_rank(r.name)
            if operator_rank < 100 and r_rank >= operator_rank:
                logger.warning(
                    f"Operator {operator_id} (rank {operator_rank}) attempted to assign role '{r.name}' (rank {r_rank})."
                )
                raise ForbiddenException(
                    message=f"Cannot assign role '{r.name}' with rank {r_rank} equal to or exceeding operator rank {operator_rank}.",
                    error_code="ROLE_RANK_ESCALATION",
                )

        # Refusal 4: Lockout protection - last Super Admin demotion refusal
        target_is_super = RoleName.SUPER_ADMIN.value in target_payload.roles
        new_has_super = any(r.name == RoleName.SUPER_ADMIN.value for r in matched_roles)
        if target_is_super and not new_has_super:
            super_count = await self.rbac_repo.count_active_super_admins()
            if super_count <= 1:
                logger.warning(
                    f"Attempted to demote the last active SUPER_ADMIN user {user_id}. Refused."
                )
                raise ConflictException(
                    message="Cannot demote the last remaining active Super Admin.",
                    error_code="CANNOT_DEMOTE_LAST_SUPER_ADMIN",
                )

        new_highest_rank = max((get_role_rank(r.name) for r in matched_roles), default=0)

        # Refusal 5 / Workflow: Non-super-admin privilege elevation requires dual authorization
        if operator_rank < 100 and new_highest_rank > target_current_rank:
            req = await self.rbac_repo.create_change_request(
                request_type="ROLE_ASSIGNMENT",
                target_user_id=user_id,
                target_role_id=None,
                requested_payload=json.dumps({"roles": [r.name for r in matched_roles]}),
                reason=reason,
                requested_by_id=operator_id,
            )
            await self.rbac_repo.db.commit()
            logger.info(
                f"Role elevation for user {user_id} queued as change request {req.id} by operator {operator_id}."
            )
            return UserRoleAssignmentResponse(
                status=True,
                message="Role elevation request submitted for hierarchical approval.",
                user_id=user_id,
                assigned_roles=target_payload.roles,
                requires_approval=True,
                request_id=req.id,
            )

        # Direct execution: Apply role assignment
        role_ids = [r.id for r in matched_roles]
        assigned_role_names = await self.rbac_repo.assign_roles_to_user(user_id, role_ids)
        await self.rbac_repo.db.commit()

        # Invalidate permission cache post-commit
        await self.invalidate_user_permissions(user_id)

        # Immediate Session Revocation on demotion or reduction
        if new_highest_rank < target_current_rank or len(matched_roles) < len(target_payload.roles):
            deactivated_count = await self.session_repo.deactivate_all_active_by_user_id(user_id)
            logger.info(
                f"Demoted user {user_id}: deactivated {deactivated_count} active sessions."
            )

        logger.info(
            f"Successfully assigned roles {assigned_role_names} to user {user_id} by operator {operator_id}."
        )

        return UserRoleAssignmentResponse(
            status=True,
            message=f"Successfully updated roles for user {target_user.username}.",
            user_id=user_id,
            assigned_roles=assigned_role_names,
            requires_approval=False,
            request_id=None,
        )

    async def assign_direct_permissions_to_user(
        self,
        operator_id: UUID,
        user_id: UUID,
        payload: AssignUserDirectPermissionsPayload,
    ) -> UserDirectPermissionsResponse:
        """
        Grants or denies direct custom permissions to a user with strict governance:
        1. Operators cannot modify their own permissions.
        2. Operators cannot modify users with equal or higher rank.
        3. Grant ceiling: Operator cannot grant permissions they do not possess.
        4. Immediate session revocation on explicit denials.
        """
        # Refusal 1: Self-mutation prevention
        if operator_id == user_id:
            raise ForbiddenException(
                message="Operators cannot modify their own direct permissions.",
                error_code="CANNOT_MODIFY_OWN_PERMISSIONS",
            )

        operator_payload = await self.get_or_cache_user_permissions(operator_id)
        operator_rank = get_user_highest_rank(operator_payload.roles)

        target_user = await self.auth_repo.get_by_id(user_id)
        if not target_user:
            raise NotFoundException(message="User not found.", error_code="USER_NOT_FOUND")

        target_payload = await self.get_or_cache_user_permissions(user_id)
        target_rank = get_user_highest_rank(target_payload.roles)

        # Refusal 2: Hierarchy check
        if operator_rank < 100 and target_rank >= operator_rank:
            raise ForbiddenException(
                message="Cannot modify permissions for users with equal or higher rank.",
                error_code="INSUFFICIENT_ROLE_RANK",
            )

        # Refusal 3: Grant ceiling check (cannot grant what you don't possess)
        if payload.is_granted and operator_rank < 100:
            operator_perms = set(operator_payload.permissions)
            for p_code in payload.permissions:
                if p_code not in operator_perms:
                    raise ForbiddenException(
                        message=f"Grant ceiling exceeded: operator does not possess permission '{p_code}'.",
                        error_code="GRANT_CEILING_EXCEEDED",
                    )

        # Resolve permissions
        matched_perms = await self.rbac_repo.resolve_permissions(payload.permissions)
        if len(matched_perms) != len(payload.permissions):
            raise BadRequestException(
                message="One or more specified permission codes/IDs do not exist or are no longer active in enums.",
                error_code="INVALID_PERMISSION_ID",
            )

        perm_ids = [p.id for p in matched_perms]
        await self.rbac_repo.assign_user_direct_permissions(
            user_id=user_id,
            permission_ids=perm_ids,
            is_granted=payload.is_granted,
            assigned_by_id=operator_id,
            reason=payload.reason,
        )
        await self.rbac_repo.db.commit()

        # Invalidate permission cache post-commit
        await self.invalidate_user_permissions(user_id)

        # Deactivate active sessions if explicit denial
        if not payload.is_granted:
            await self.session_repo.deactivate_all_active_by_user_id(user_id)

        updated_summary = await self.rbac_repo.get_user_roles_and_permissions(user_id)

        return UserDirectPermissionsResponse(
            status=True,
            message=f"Successfully updated direct permissions for user {target_user.username}.",
            user_id=user_id,
            direct_grants=updated_summary.get("direct_grants", []),
            direct_revocations=updated_summary.get("direct_revocations", []),
        )

    async def remove_direct_permissions_from_user(
        self,
        operator_id: UUID,
        user_id: UUID,
        permissions: Sequence[str],
        reason: str,
    ) -> UserDirectPermissionsResponse:
        """Removes direct permission overrides for a user."""
        if operator_id == user_id:
            raise ForbiddenException(
                message="Operators cannot modify their own direct permissions.",
                error_code="CANNOT_MODIFY_OWN_PERMISSIONS",
            )

        operator_payload = await self.get_or_cache_user_permissions(operator_id)
        operator_rank = get_user_highest_rank(operator_payload.roles)

        target_user = await self.auth_repo.get_by_id(user_id)
        if not target_user:
            raise NotFoundException(message="User not found.", error_code="USER_NOT_FOUND")

        target_payload = await self.get_or_cache_user_permissions(user_id)
        target_rank = get_user_highest_rank(target_payload.roles)

        if operator_rank < 100 and target_rank >= operator_rank:
            raise ForbiddenException(
                message="Cannot modify permissions for users with equal or higher rank.",
                error_code="INSUFFICIENT_ROLE_RANK",
            )

        matched_perms = await self.rbac_repo.resolve_permissions(permissions)
        if len(matched_perms) != len(permissions):
            raise BadRequestException(
                message="One or more specified permission codes/IDs do not exist or are no longer active in enums.",
                error_code="INVALID_PERMISSION_ID",
            )

        perm_ids = [p.id for p in matched_perms]
        await self.rbac_repo.remove_user_direct_permissions(user_id, perm_ids)
        await self.rbac_repo.db.commit()

        await self.invalidate_user_permissions(user_id)

        updated_summary = await self.rbac_repo.get_user_roles_and_permissions(user_id)

        return UserDirectPermissionsResponse(
            status=True,
            message=f"Successfully removed direct permission overrides for user {target_user.username}.",
            user_id=user_id,
            direct_grants=updated_summary.get("direct_grants", []),
            direct_revocations=updated_summary.get("direct_revocations", []),
        )

    async def assign_permissions_to_role(
        self,
        operator_id: UUID,
        role_identifier: str,
        permission_identifiers: Sequence[str],
        reason: str,
    ) -> RolePermissionAssignmentResponse:
        """
        Replaces assigned permissions for a given role:
        1. SUPER_ADMIN role permissions are immutable.
        2. Operator cannot edit roles with rank equal to or exceeding their own rank.
        3. Operator cannot grant permissions they do not possess (grant ceiling).
        4. Flushes Redis caches for all users holding this role.
        """
        role = await self.rbac_repo.get_role_by_identifier(role_identifier)
        if not role:
            logger.warning(f"Role '{role_identifier}' not found or inactive for permission assignment.")
            raise NotFoundException(
                message="Role not found or is no longer active in enums.",
                error_code="ROLE_NOT_FOUND",
            )

        # Refusal 1: Immutability of SUPER_ADMIN permissions
        if role.name == RoleName.SUPER_ADMIN.value:
            logger.warning("Attempted mutation of immutable SUPER_ADMIN role permissions.")
            raise ForbiddenException(
                message="Super Admin role permissions are immutable and cannot be altered.",
                error_code="SUPER_ADMIN_IMMUTABLE",
            )

        # Operator rank check
        operator_payload = await self.get_or_cache_user_permissions(operator_id)
        operator_rank = get_user_highest_rank(operator_payload.roles)
        role_rank = get_role_rank(role.name)

        # Refusal 2: Hierarchy check
        if operator_rank < 100 and role_rank >= operator_rank:
            raise ForbiddenException(
                message=f"Cannot modify permissions for role '{role.name}' with rank {role_rank} equal to or exceeding operator rank {operator_rank}.",
                error_code="ROLE_RANK_ESCALATION",
            )

        # Refusal 3: Grant ceiling check
        if operator_rank < 100:
            operator_perms = set(operator_payload.permissions)
            for p_code in permission_identifiers:
                if p_code not in operator_perms:
                    raise ForbiddenException(
                        message=f"Grant ceiling exceeded: operator does not possess permission '{p_code}'.",
                        error_code="GRANT_CEILING_EXCEEDED",
                    )

        # Resolve permission codes or UUIDs
        matched_perms = []
        if permission_identifiers:
            matched_perms = await self.rbac_repo.resolve_permissions(permission_identifiers)
            if len(matched_perms) != len(permission_identifiers):
                raise BadRequestException(
                    message="One or more specified permission codes/IDs do not exist or are no longer active in enums.",
                    error_code="INVALID_PERMISSION_ID",
                )

        perm_ids = [p.id for p in matched_perms]
        assigned_perm_codes = await self.rbac_repo.assign_permissions_to_role(
            role.id, perm_ids
        )

        await self.rbac_repo.db.commit()

        # Invalidate cache post-commit for all users holding this role
        affected_user_ids = await self.rbac_repo.get_user_ids_by_role(role.id)
        for u_id in affected_user_ids:
            await self.invalidate_user_permissions(u_id)

        logger.info(
            f"Updated permissions for role '{role.name}' and invalidated cache for {len(affected_user_ids)} users."
        )

        return RolePermissionAssignmentResponse(
            status=True,
            message=f"Successfully updated permissions for role '{role.name}'.",
            role_id=role.id,
            role_name=role.name,
            assigned_permissions=assigned_perm_codes,
            requires_approval=False,
            request_id=None,
        )

    async def batch_assign_role_permissions(
        self,
        operator_id: UUID,
        payload: BatchRolePermissionAssignmentPayload,
    ) -> BatchRolePermissionAssignmentResponse:
        """Atomically updates permissions across multiple roles in a single operation."""
        operator_payload = await self.get_or_cache_user_permissions(operator_id)
        operator_rank = get_user_highest_rank(operator_payload.roles)
        operator_perms = set(operator_payload.permissions)

        updated_role_names: List[str] = []
        all_affected_user_ids: set[UUID] = set()

        for item in payload.assignments:
            role = await self.rbac_repo.get_role_by_identifier(item.role)
            if not role:
                raise NotFoundException(
                    message=f"Role '{item.role}' not found or inactive.",
                    error_code="ROLE_NOT_FOUND",
                )

            if role.name == RoleName.SUPER_ADMIN.value:
                raise ForbiddenException(
                    message="Super Admin role permissions are immutable and cannot be altered.",
                    error_code="SUPER_ADMIN_IMMUTABLE",
                )

            role_rank = get_role_rank(role.name)
            if operator_rank < 100 and role_rank >= operator_rank:
                raise ForbiddenException(
                    message=f"Cannot modify permissions for role '{role.name}' with rank {role_rank} equal to or exceeding operator rank {operator_rank}.",
                    error_code="ROLE_RANK_ESCALATION",
                )

            if operator_rank < 100:
                for p_code in item.permissions:
                    if p_code not in operator_perms:
                        raise ForbiddenException(
                            message=f"Grant ceiling exceeded: operator does not possess permission '{p_code}'.",
                            error_code="GRANT_CEILING_EXCEEDED",
                        )

            matched_perms = []
            if item.permissions:
                matched_perms = await self.rbac_repo.resolve_permissions(item.permissions)
                if len(matched_perms) != len(item.permissions):
                    raise BadRequestException(
                        message=f"One or more permission codes for role '{item.role}' do not exist or are inactive.",
                        error_code="INVALID_PERMISSION_ID",
                    )

            perm_ids = [p.id for p in matched_perms]
            await self.rbac_repo.assign_permissions_to_role(role.id, perm_ids)
            updated_role_names.append(role.name)

            affected_users = await self.rbac_repo.get_user_ids_by_role(role.id)
            all_affected_user_ids.update(affected_users)

        await self.rbac_repo.db.commit()

        for u_id in all_affected_user_ids:
            await self.invalidate_user_permissions(u_id)

        logger.info(
            f"Batch assigned permissions for roles: {updated_role_names}. Invalidated {len(all_affected_user_ids)} user caches."
        )

        return BatchRolePermissionAssignmentResponse(
            status=True,
            message=f"Successfully batch updated permissions for {len(updated_role_names)} roles.",
            updated_roles=updated_role_names,
        )

    async def reset_role_to_defaults(
        self,
        operator_id: UUID,
        role_identifier: str,
    ) -> RolePermissionAssignmentResponse:
        """Resets a role's permissions back to its code-defined ROLE_DEFAULT_PERMISSIONS preset."""
        role = await self.rbac_repo.get_role_by_identifier(role_identifier)
        if not role:
            raise NotFoundException(
                message=f"Role '{role_identifier}' not found.",
                error_code="ROLE_NOT_FOUND",
            )

        if role.name == RoleName.SUPER_ADMIN.value:
            raise ForbiddenException(
                message="Super Admin role permissions are immutable and cannot be altered.",
                error_code="SUPER_ADMIN_IMMUTABLE",
            )

        try:
            r_enum = RoleName(role.name)
        except ValueError:
            raise BadRequestException(
                message=f"Role '{role.name}' is not a defined system role enum.",
                error_code="ROLE_NOT_FOUND",
            )

        default_perms = ROLE_DEFAULT_PERMISSIONS.get(r_enum, set())
        perm_codes = [p.value for p in default_perms]
        return await self.assign_permissions_to_role(
            operator_id=operator_id,
            role_identifier=role.name,
            permission_identifiers=perm_codes,
            reason="Reset to code-defined default permissions.",
        )

    async def list_pending_change_requests(
        self,
        operator_id: UUID,
    ) -> List[RBACChangeRequestResponse]:
        """Lists pending change requests awaiting review."""
        requests = await self.rbac_repo.get_pending_change_requests()
        return [
            RBACChangeRequestResponse(
                id=req.id,
                request_type=req.request_type,
                target_user_id=req.target_user_id,
                target_role_id=req.target_role_id,
                requested_payload=req.requested_payload,
                status=req.status.value if hasattr(req.status, "value") else str(req.status),
                reason=req.reason,
                requested_by_id=req.requested_by_id,
                reviewed_by_id=req.reviewed_by_id,
                review_notes=req.review_notes,
                created_at=req.created_at,
                reviewed_at=req.reviewed_at,
            )
            for req in requests
        ]

    async def review_change_request(
        self,
        operator_id: UUID,
        request_id: UUID,
        payload: ReviewChangeRequestPayload,
        is_approved: bool,
    ) -> RBACChangeRequestResponse:
        """
        Reviews and processes an RBAC change request.
        Adheres to hierarchical authority:
        - Self-approval is strictly forbidden (dual control).
        - Reviewer's rank must strictly exceed requester's rank.
        - Reviewer's rank must be equal to or exceed requested role's rank.
        """
        req = await self.rbac_repo.get_change_request_by_id(request_id)
        if not req:
            raise NotFoundException(
                message="Change request not found.",
                error_code="CHANGE_REQUEST_NOT_FOUND",
            )

        if req.status != RBACChangeRequestStatus.PENDING:
            raise ConflictException(
                message=f"Change request is already {req.status.value}.",
                error_code="CHANGE_REQUEST_ALREADY_PROCESSED",
            )

        # Dual Control: Refuse self-approval
        if req.requested_by_id == operator_id:
            raise ForbiddenException(
                message="Operators cannot approve their own change requests (dual-control violation).",
                error_code="CANNOT_SELF_APPROVE",
            )

        # Hierarchical Authority Check
        operator_payload = await self.get_or_cache_user_permissions(operator_id)
        operator_rank = get_user_highest_rank(operator_payload.roles)

        requester_payload = await self.get_or_cache_user_permissions(req.requested_by_id)
        requester_rank = get_user_highest_rank(requester_payload.roles)

        if operator_rank < 100 and operator_rank <= requester_rank:
            raise ForbiddenException(
                message="Insufficient rank to review this change request. Reviewer rank must exceed requester rank.",
                error_code="INSUFFICIENT_REVIEWER_RANK",
            )

        parsed_data = json.loads(req.requested_payload) if req.requested_payload else {}

        if is_approved:
            if req.request_type == "ROLE_ASSIGNMENT" and req.target_user_id:
                requested_roles = parsed_data.get("roles", [])
                max_req_rank = max((get_role_rank(r) for r in requested_roles), default=0)
                if operator_rank < 100 and operator_rank < max_req_rank:
                    raise ForbiddenException(
                        message="Reviewer rank must be equal to or higher than the requested role rank.",
                        error_code="INSUFFICIENT_REVIEWER_RANK",
                    )

                matched_roles = await self.rbac_repo.resolve_roles(requested_roles)
                role_ids = [r.id for r in matched_roles]
                await self.rbac_repo.assign_roles_to_user(req.target_user_id, role_ids)

            req.status = RBACChangeRequestStatus.APPROVED
            req.reviewed_by_id = operator_id
            req.review_notes = payload.review_notes
            req.reviewed_at = datetime.now(timezone.utc)
            await self.rbac_repo.db.commit()

            if req.target_user_id:
                await self.invalidate_user_permissions(req.target_user_id)
        else:
            req.status = RBACChangeRequestStatus.REJECTED
            req.reviewed_by_id = operator_id
            req.review_notes = payload.review_notes
            req.reviewed_at = datetime.now(timezone.utc)
            await self.rbac_repo.db.commit()

        logger.info(
            f"Change request {request_id} was {'APPROVED' if is_approved else 'REJECTED'} by operator {operator_id}."
        )

        return RBACChangeRequestResponse(
            id=req.id,
            request_type=req.request_type,
            target_user_id=req.target_user_id,
            target_role_id=req.target_role_id,
            requested_payload=req.requested_payload,
            status=req.status.value if hasattr(req.status, "value") else str(req.status),
            reason=req.reason,
            requested_by_id=req.requested_by_id,
            reviewed_by_id=req.reviewed_by_id,
            review_notes=req.review_notes,
            created_at=req.created_at,
            reviewed_at=req.reviewed_at,
        )

    async def sync_enums_to_db(self) -> dict:
        """Invokes idempotent synchronization of enums with database tables."""
        return await self.rbac_repo.sync_enums_to_db()
