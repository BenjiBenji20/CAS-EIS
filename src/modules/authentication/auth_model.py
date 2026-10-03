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


class User(Base, TimestampMixin):
    """Core identity and authentication record."""

    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    id: Mapped[uuid_pk]
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
