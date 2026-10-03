from datetime import datetime
from typing import List, Optional
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin, uuid_pk
from modules.eis.eis_enums import (
    EisResultStatus,
    EisTransmissionStatus,
)


class EisSession(Base, TimestampMixin):
    """Audit and token lifecycle storage for BIR EIS authentication sessions."""

    __tablename__ = "eis_sessions"
    __table_args__ = {"schema": "eis"}

    id: Mapped[uuid_pk]
    auth_token: Mapped[str] = mapped_column(String(500), nullable=False)
    session_key: Mapped[str] = mapped_column(String(64), nullable=False)
    token_expiry: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class EisTransmission(Base, TimestampMixin):
    """Audit record for a batch transmission attempt sent to BIR EIS."""

    __tablename__ = "eis_transmissions"
    __table_args__ = {"schema": "eis"}

    id: Mapped[uuid_pk]
    submit_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)

    # Re-transmission tracking: links retry transmission back to original parent transmission
    parent_transmission_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eis.eis_transmissions.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[EisTransmissionStatus] = mapped_column(
        Enum(EisTransmissionStatus, native_enum=True),
        default=EisTransmissionStatus.PENDING,
        index=True,
        nullable=False,
    )

    ack_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    invoice_count: Mapped[int] = mapped_column(Integer, nullable=False)
    process_status_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)

    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Guidelines compliant: stores AES-encrypted request payload and raw BIR response
    raw_request: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    items: Mapped[List["EisTransmissionItem"]] = relationship(
        "EisTransmissionItem",
        back_populates="transmission",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class EisTransmissionItem(Base, TimestampMixin):
    """Per-invoice validation result returned by BIR EIS inquiry."""

    __tablename__ = "eis_transmission_items"
    __table_args__ = {"schema": "eis"}

    id: Mapped[uuid_pk]
    transmission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eis.eis_transmissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    eis_unique_id: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    comp_invoice_id: Mapped[str] = mapped_column(String(50), nullable=False)

    result_status: Mapped[EisResultStatus] = mapped_column(
        Enum(EisResultStatus, native_enum=True),
        nullable=False,
    )
    fail_reason_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    fail_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship back to parent batch transmission
    transmission: Mapped[EisTransmission] = relationship(
        "EisTransmission",
        back_populates="items",
    )
