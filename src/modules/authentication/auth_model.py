from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, List, Optional
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from modules.profile.user_profile_model import UserProfile
    from modules.session.session_model import UserSession


class UserStatus(str, PyEnum):
    """User account lifecycle status."""
    PENDING = "PENDING"      # Registration submitted, awaiting approval
    ACTIVE = "ACTIVE"        # Normal active user
    INACTIVE = "INACTIVE"    # Deactivated account
    SUSPENDED = "SUSPENDED"  # Suspended due to security or administrative reasons


class Permission(Base, TimestampMixin):
    """Granular permission code definition (e.g. accounting:journal:post)."""

    __tablename__ = "permissions"
    __table_args__ = {"schema": "auth"}

    id: Mapped[uuid_pk]
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    module: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Many-to-Many: Permission <-> Role (via auth.role_permissions junction table)
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary="auth.role_permissions",
        back_populates="permissions",
    )


class RolePermission(Base, TimestampMixin):
    """Junction table mapping Roles to Permissions (Many-to-Many)."""

    __tablename__ = "role_permissions"
    __table_args__ = {"schema": "auth"}

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Role(Base, TimestampMixin):
    """User role holding a batch of permissions."""

    __tablename__ = "roles"
    __table_args__ = {"schema": "auth"}

    id: Mapped[uuid_pk]
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_system_role: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Many-to-Many: Role <-> Permission (via auth.role_permissions junction table)
    permissions: Mapped[List[Permission]] = relationship(
        "Permission",
        secondary="auth.role_permissions",
        back_populates="roles",
        lazy="selectin",
    )
    # Many-to-Many: Role <-> User (via auth.user_roles junction table)
    users: Mapped[List["User"]] = relationship(
        "User",
        secondary="auth.user_roles",
        back_populates="roles",
    )


class UserRole(Base, TimestampMixin):
    """Junction table mapping Users to Roles (Many-to-Many)."""

    __tablename__ = "user_roles"
    __table_args__ = {"schema": "auth"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.roles.id", ondelete="CASCADE"),
        primary_key=True,
    )


class UserPermission(Base, TimestampMixin):
    """Direct user permission grants / denials (Many-to-Many)."""

    __tablename__ = "user_permissions"
    __table_args__ = {"schema": "auth"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_granted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assigned_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationship to Permission model
    permission: Mapped[Permission] = relationship(
        "Permission",
        foreign_keys=[permission_id],
        lazy="selectin",
    )


class RBACChangeRequestStatus(str, PyEnum):
    """Status for dual-authorization RBAC change requests."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RBACChangeRequest(Base, TimestampMixin):
    """Dual-authorization RBAC change request."""

    __tablename__ = "rbac_change_requests"
    __table_args__ = {"schema": "auth"}

    id: Mapped[uuid_pk]
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ROLE_ASSIGNMENT, DIRECT_PERMISSION
    target_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=True,
    )
    target_role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.roles.id", ondelete="CASCADE"),
        nullable=True,
    )
    requested_payload: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[RBACChangeRequestStatus] = mapped_column(
        Enum(RBACChangeRequestStatus, native_enum=True),
        default=RBACChangeRequestStatus.PENDING,
        index=True,
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    review_notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class User(Base, TimestampMixin):
    """Core identity and authentication record."""

    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    id: Mapped[uuid_pk]
    user_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        index=True,
        nullable=False,
        server_default=text("'USR-' || lpad(nextval('auth.user_code_seq')::text, 5, '0')"),
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, native_enum=True),
        default=UserStatus.PENDING,
        index=True,
        nullable=False,
    )

    banned_until_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # Many-to-Many: User <-> Role (via auth.user_roles junction table)
    roles: Mapped[List[Role]] = relationship(
        "Role",
        secondary="auth.user_roles",
        back_populates="users",
        lazy="selectin",
    )
    # One-to-Many: User (1) -> UserSession (N)
    sessions: Mapped[List["UserSession"]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    # One-to-One: User (1) <-> UserProfile (1)
    profile: Mapped[Optional["UserProfile"]] = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    # One-to-Many: User (1) -> UserPermission (N)
    direct_permissions: Mapped[List[UserPermission]] = relationship(
        "UserPermission",
        foreign_keys="[UserPermission.user_id]",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
