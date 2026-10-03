from datetime import datetime, timezone
from typing import Annotated
import uuid
from sqlalchemy import DateTime, MetaData
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Standard metadata naming convention for database constraints
# Ensures deterministic constraint names across Alembic migrations
POSTGRES_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy 2.0 ORM models."""

    metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)


def generate_uuid() -> uuid.UUID:
    """Generates a UUID, prioritizing time-ordered UUIDv7 if uuid6 library is available."""
    try:
        import uuid6

        return uuid6.uuid7()
    except ImportError:
        return uuid.uuid4()


# Reusable Type Annotations for modern model declarations
uuid_pk = Annotated[
    uuid.UUID,
    mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    ),
]


class TimestampMixin:
    """Mixin for models requiring created_at and updated_at timestamps in UTC."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
