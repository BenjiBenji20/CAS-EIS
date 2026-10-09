from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import Field

from base.schema import BaseSchema

class SessionLogoutResponse(BaseSchema):
    """Response confirming session deactivation."""
    status: bool = True
    description: str
    session_id: Optional[UUID] = None
    revoked_count: Optional[int] = None


class SessionUserInfo(BaseSchema):
    """Identity and role metadata of the session owner."""
    user_id: UUID
    user_code: str = Field(description="Human-friendly user code (e.g. USR-00001)")
    username: str
    email: str
    status: str
    roles: list[str] = Field(default_factory=list, description="Assigned role names (e.g. SUPER_ADMIN, STAFF_USER)")
    full_name: Optional[str] = Field(default=None, description="Formatted first and last name from UserProfile")


class AdminUserSessionListItemResponse(BaseSchema):
    """Enriched session record for administrative monitoring and auditing."""
    id: UUID
    user_id: UUID
    is_active: bool
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    expires_at: datetime
    last_active_at: datetime
    created_at: datetime
    user: SessionUserInfo
