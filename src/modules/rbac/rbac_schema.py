from typing import List, Optional
from uuid import UUID
from pydantic import Field

from base.schema import BaseSchema


class UserPermissionsCachePayload(BaseSchema):
    """Schema representing cached user roles and permissions in Redis."""
    user_id: UUID = Field(..., description="UUID of the user")
    roles: List[str] = Field(default_factory=list, description="List of assigned role names")
    permissions: List[str] = Field(default_factory=list, description="List of assigned permission codes")


class ActionSchema(BaseSchema):
    """Schema for individual action and its canonical permission code."""
    name: str = Field(..., description="Action name (e.g. ACCEPT, CREATE, POST)")
    description: str = Field(..., description="Human-readable action description")
    permission: str = Field(..., description="Canonical permission code (MODULE:RESOURCE:ACTION)")


class ResourceSchema(BaseSchema):
    """Schema for endpoint / entity resource containing actions."""
    name: str = Field(..., description="Resource name (e.g. REGISTRATION, USER)")
    description: str = Field(..., description="Human-readable resource description")
    actions: List[ActionSchema] = Field(default_factory=list, description="Actions available on this resource")


class ModuleSchema(BaseSchema):
    """Schema for high-level system module containing resources."""
    name: str = Field(..., description="Module name (e.g. AUTHENTICATION, PROFILE)")
    description: str = Field(..., description="Human-readable module description")
    resources: List[ResourceSchema] = Field(default_factory=list, description="Resources under this module")


class RoleOverviewSchema(BaseSchema):
    """Schema for system role with description and active permission codes."""
    id: UUID = Field(..., description="Database UUID of the role")
    name: str = Field(..., description="Role name (e.g. ADMIN, STAFF_USER)")
    description: Optional[str] = Field(None, description="Human-readable role description")
    is_system_role: bool = Field(False, description="Whether this is an immutable system role")
    permissions: List[str] = Field(default_factory=list, description="Assigned canonical permission codes")


class RBACConfigResponse(BaseSchema):
    """
    Unified configuration response providing both the hierarchical permission
    tree and all active system roles with their granted permissions.
    """
    modules: List[ModuleSchema] = Field(..., description="Hierarchical module/resource/action tree")
    roles: List[RoleOverviewSchema] = Field(..., description="All active roles and their granted permissions")


class UserRBACSummaryResponse(BaseSchema):
    """Summary of a user's roles and effective permissions."""
    user_id: UUID
    user_code: Optional[str] = None
    username: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)


class AssignUserRolesPayload(BaseSchema):
    """Request payload for assigning roles to a user (accepts role names or UUIDs)."""
    roles: List[str] = Field(
        ...,
        min_length=1,
        description="List of role names (e.g. 'ADMIN') or role UUIDs to assign",
    )


class AssignRolePermissionsPayload(BaseSchema):
    """Request payload for assigning permissions to a role (accepts permission codes or UUIDs)."""
    permissions: List[str] = Field(
        default_factory=list,
        description="List of canonical permission codes (e.g. 'AUTHENTICATION:USER:READ') or UUIDs",
    )


class RoleAssignmentItem(BaseSchema):
    """Single role assignment specification for batch processing."""
    role: str = Field(..., description="Target role name or UUID")
    permissions: List[str] = Field(default_factory=list, description="List of permission codes or UUIDs")


class BatchRolePermissionAssignmentPayload(BaseSchema):
    """Request payload for batch updating permissions across multiple roles."""
    assignments: List[RoleAssignmentItem] = Field(..., min_length=1, description="List of role permission assignments")


class UserRoleAssignmentResponse(BaseSchema):
    """Response returned upon assigning roles to a user."""
    status: bool = True
    message: str
    user_id: UUID
    assigned_roles: List[str] = Field(default_factory=list)


class RolePermissionAssignmentResponse(BaseSchema):
    """Response returned upon assigning permissions to a role."""
    status: bool = True
    message: str
    role_id: UUID
    role_name: str
    assigned_permissions: List[str] = Field(default_factory=list)


class BatchRolePermissionAssignmentResponse(BaseSchema):
    """Response returned upon batch updating role permissions."""
    status: bool = True
    message: str
    updated_roles: List[str] = Field(default_factory=list)
