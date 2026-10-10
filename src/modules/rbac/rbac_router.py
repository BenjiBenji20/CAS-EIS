from uuid import UUID

from dependencies.rbac_guard import require_role
from fastapi import APIRouter, Depends, status
from modules.rbac.rbac_schema import (
    AssignRolePermissionsPayload,
    AssignUserRolesPayload,
    BatchRolePermissionAssignmentPayload,
    BatchRolePermissionAssignmentResponse,
    RBACConfigResponse,
    RolePermissionAssignmentResponse,
    UserRBACSummaryResponse,
    UserRoleAssignmentResponse,
)
from modules.rbac.rbac_service import RBACService
from shares.enums import RoleName

router = APIRouter(prefix="/api/private/admin/rbac", tags=["RBAC Administration"])


@router.get(
    "",
    summary="Get unified RBAC hierarchy and active system roles with permissions.",
    status_code=status.HTTP_200_OK,
    response_model=RBACConfigResponse,
    dependencies=[Depends(require_role(RoleName.SUPER_ADMIN, RoleName.ADMIN))],
)
async def get_rbac_configuration(
    service: RBACService = Depends(),
) -> RBACConfigResponse:
    """
    Returns the complete system RBAC structure:
    - Hierarchical Module -> Resource -> Action tree directly from code enums.
    - All active database roles and their assigned permission codes.
    """
    return await service.get_rbac_configuration()


@router.get(
    "/users/{user_id}",
    summary="Retrieve user's assigned roles and resolved effective permissions.",
    status_code=status.HTTP_200_OK,
    response_model=UserRBACSummaryResponse,
    dependencies=[Depends(require_role(RoleName.SUPER_ADMIN, RoleName.ADMIN))],
)
async def get_user_rbac_summary(
    user_id: UUID,
    service: RBACService = Depends(),
) -> UserRBACSummaryResponse:
    """Retrieve user identity details, assigned roles, and resolved permissions."""
    return await service.get_user_rbac_summary(user_id=user_id)


@router.put(
    "/users/{user_id}/roles",
    summary="Assign / update roles for a specific user and invalidate permission cache.",
    status_code=status.HTTP_200_OK,
    response_model=UserRoleAssignmentResponse,
    dependencies=[Depends(require_role(RoleName.SUPER_ADMIN, RoleName.ADMIN))],
)
async def assign_user_roles(
    user_id: UUID,
    payload: AssignUserRolesPayload,
    service: RBACService = Depends(),
) -> UserRoleAssignmentResponse:
    """Replaces user's assigned roles (accepts role names or UUIDs) and immediately flushes cache."""
    return await service.assign_roles_to_user(user_id=user_id, role_identifiers=payload.roles)


@router.put(
    "/roles/{role_identifier}/permissions",
    summary="Assign / update permissions for a role and invalidate affected user caches.",
    status_code=status.HTTP_200_OK,
    response_model=RolePermissionAssignmentResponse,
    dependencies=[Depends(require_role(RoleName.SUPER_ADMIN, RoleName.ADMIN))],
)
async def assign_role_permissions(
    role_identifier: str,
    payload: AssignRolePermissionsPayload,
    service: RBACService = Depends(),
) -> RolePermissionAssignmentResponse:
    """Replaces permissions for a role (by role name or UUID) and invalidates Redis cache."""
    return await service.assign_permissions_to_role(
        role_identifier=role_identifier, permission_identifiers=payload.permissions
    )


@router.post(
    "/roles/batch-assign-permissions",
    summary="Batch update permissions across multiple roles in a single operation.",
    status_code=status.HTTP_200_OK,
    response_model=BatchRolePermissionAssignmentResponse,
    dependencies=[Depends(require_role(RoleName.SUPER_ADMIN, RoleName.ADMIN))],
)
async def batch_assign_role_permissions(
    payload: BatchRolePermissionAssignmentPayload,
    service: RBACService = Depends(),
) -> BatchRolePermissionAssignmentResponse:
    """Atomically updates permissions for multiple roles and flushes affected user caches."""
    return await service.batch_assign_role_permissions(payload=payload)


@router.post(
    "/roles/{role_identifier}/reset-defaults",
    summary="Reset a role's permissions back to its code-defined default preset.",
    status_code=status.HTTP_200_OK,
    response_model=RolePermissionAssignmentResponse,
    dependencies=[Depends(require_role(RoleName.SUPER_ADMIN, RoleName.ADMIN))],
)
async def reset_role_to_defaults(
    role_identifier: str,
    service: RBACService = Depends(),
) -> RolePermissionAssignmentResponse:
    """Reverts a system role's permissions to its default preset defined in enums.py."""
    return await service.reset_role_to_defaults(role_identifier=role_identifier)
