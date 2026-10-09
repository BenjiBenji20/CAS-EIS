from typing import List, Optional
from uuid import UUID
from pydantic import Field

from base.schema import BaseSchema


class UserPermissionsCachePayload(BaseSchema):
    """Schema representing cached user roles and permissions in Redis."""
    user_id: UUID = Field(..., description="UUID of the user")
    roles: List[str] = Field(default_factory=list, description="List of assigned role names")
    permissions: List[str] = Field(default_factory=list, description="List of assigned permission codes")


class PermissionResponse(BaseSchema):
    """Schema for returning permission details."""
    id: UUID
    code: str
    module: str
    name: str
    description: Optional[str] = None


class RoleResponse(BaseSchema):
    """Schema for returning role details."""
    id: UUID
    name: str
    description: Optional[str] = None
    is_system_role: bool = False
    permissions: List[PermissionResponse] = Field(default_factory=list)


class AssignRoleRequest(BaseSchema):
    """Request payload for assigning roles to a user (Superadmin endpoint)."""
    user_id: UUID
    role_ids: List[UUID]


class AssignPermissionRequest(BaseSchema):
    """Request payload for assigning permissions to a role (Superadmin endpoint)."""
    role_id: UUID
    permission_ids: List[UUID]
