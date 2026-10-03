from datetime import date
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import Date, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from modules.authentication.auth_model import User


class UserGender(str, PyEnum):
    """User gender identity representation."""
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHERS = "OTHERS"


class UserProfile(Base, TimestampMixin):
    """Personal profile details for users (1-to-1 extension of auth.users)."""

    __tablename__ = "user_profiles"
    __table_args__ = {"schema": "profile"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Personal details
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    middle_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    suffix: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    nickname: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    gender: Mapped[UserGender] = mapped_column(
        Enum(UserGender, native_enum=True),
        nullable=False,
    )
    cellphone_number: Mapped[str] = mapped_column(String(20), nullable=False)

    # Structured address fields
    street: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    province_state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), default="Philippines", nullable=True)

    # One-to-One: UserProfile (1) <-> User (1)
    user: Mapped["User"] = relationship("User", back_populates="profile")
