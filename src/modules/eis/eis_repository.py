from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple
import uuid

from fastapi import Depends
from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from base.repository import BaseRepository
from db.db_session import get_async_db
from exceptions.app_exception import InternalServerException
from modules.eis.eis_enums import EisTransmissionStatus
from modules.eis.eis_model import EisSession, EisTransmission, EisTransmissionItem


class EisSessionRepository(BaseRepository[EisSession]):
    """Database repository for BIR EIS authentication sessions."""

    def __init__(self, db: AsyncSession = Depends(get_async_db)):
        super().__init__(db, EisSession)

    async def get_active_session(self) -> Optional[EisSession]:
        """Fetch the current active session record."""
        try:
            stmt = (
                select(EisSession)
                .where(EisSession.is_active == True)  # noqa: E712
                .order_by(EisSession.created_at.desc())
                .limit(1)
            )
            result = await self.db.execute(stmt)
            return result.scalars().first()
        except Exception as e:
            logger.error(f"Error fetching active EIS session: {e}")
            raise InternalServerException(
                message="Error retrieving active EIS session",
                error_code="EIS_SESSION_QUERY_FAILED",
            )

    async def deactivate_all(self, *, commit: bool = False) -> None:
        """Deactivate all existing active sessions before storing a fresh one."""
        try:
            stmt = (
                update(EisSession)
                .where(EisSession.is_active == True)  # noqa: E712
                .values(is_active=False)
            )
            await self.db.execute(stmt)
            if commit:
                await self.db.commit()
            else:
                await self.db.flush()
        except Exception as e:
            logger.error(f"Error deactivating old EIS sessions: {e}")
            raise InternalServerException(
                message="Error deactivating old EIS sessions",
                error_code="EIS_SESSION_DEACTIVATE_FAILED",
            )

    async def create_session(
        self,
        auth_token: str,
        session_key: str,
        token_expiry: datetime,
        *,
        commit: bool = True,
    ) -> EisSession:
        """Deactivate any prior sessions and record the newly authenticated session."""
        try:
            await self.deactivate_all(commit=False)
            session = EisSession(
                auth_token=auth_token,
                session_key=session_key,
                token_expiry=token_expiry,
                is_active=True,
            )
            self.db.add(session)
            if commit:
                await self.db.commit()
                await self.db.refresh(session)
            else:
                await self.db.flush()
            return session
        except Exception as e:
            logger.error(f"Error saving new EIS session: {e}")
            raise InternalServerException(
                message="Error saving new EIS session",
                error_code="EIS_SESSION_CREATE_FAILED",
            )


class EisTransmissionRepository(BaseRepository[EisTransmission]):
    """Database repository for BIR EIS batch submissions."""

    def __init__(self, db: AsyncSession = Depends(get_async_db)):
        super().__init__(db, EisTransmission)

    async def get_by_submit_id(self, submit_id: str) -> Optional[EisTransmission]:
        """Fetch transmission record by submitId including all per-invoice items."""
        try:
            stmt = (
                select(EisTransmission)
                .options(selectinload(EisTransmission.items))
                .where(EisTransmission.submit_id == submit_id)
                .limit(1)
            )
            result = await self.db.execute(stmt)
            return result.scalars().first()
        except Exception as e:
            logger.error(f"Error fetching transmission by submit_id {submit_id}: {e}")
            raise InternalServerException(
                message="Error retrieving transmission audit record",
                error_code="EIS_TRANSMISSION_QUERY_FAILED",
            )

    async def get_pending_transmissions(self) -> Sequence[EisTransmission]:
        """Fetch all transmissions currently in PENDING or SENT status."""
        try:
            stmt = (
                select(EisTransmission)
                .where(
                    EisTransmission.status.in_(
                        [EisTransmissionStatus.PENDING, EisTransmissionStatus.SENT]
                    )
                )
                .order_by(EisTransmission.created_at.asc())
            )
            result = await self.db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching pending transmissions: {e}")
            raise InternalServerException(
                message="Error retrieving pending transmissions",
                error_code="EIS_PENDING_QUERY_FAILED",
            )

    async def update_status(
        self,
        transmission: EisTransmission,
        *,
        status: EisTransmissionStatus,
        ack_id: Optional[str] = None,
        process_status_code: Optional[str] = None,
        raw_response: Optional[str] = None,
        acknowledged_at: Optional[datetime] = None,
        commit: bool = True,
    ) -> EisTransmission:
        """Update transmission status and inquiry timestamps."""
        try:
            transmission.status = status
            if ack_id is not None:
                transmission.ack_id = ack_id
            if process_status_code is not None:
                transmission.process_status_code = process_status_code
            if raw_response is not None:
                transmission.raw_response = raw_response
            if acknowledged_at is not None:
                transmission.acknowledged_at = acknowledged_at

            self.db.add(transmission)
            if commit:
                await self.db.commit()
                await self.db.refresh(transmission)
            else:
                await self.db.flush()
            return transmission
        except Exception as e:
            logger.error(f"Error updating transmission {transmission.id} status: {e}")
            raise InternalServerException(
                message="Error updating transmission status",
                error_code="EIS_TRANSMISSION_UPDATE_FAILED",
            )

    async def get_transmissions_paginated(
        self,
        status: Optional[EisTransmissionStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[Sequence[EisTransmission], int]:
        """Fetch paginated list of transmissions with total count."""
        try:
            count_query = select(func.count(EisTransmission.id))
            stmt = (
                select(EisTransmission)
                .options(selectinload(EisTransmission.items))
                .order_by(EisTransmission.created_at.desc())
                .limit(limit)
                .offset(offset)
            )

            if status is not None:
                count_query = count_query.where(EisTransmission.status == status)
                stmt = stmt.where(EisTransmission.status == status)

            count_res = await self.db.execute(count_query)
            total = count_res.scalar() or 0

            result = await self.db.execute(stmt)
            records = result.scalars().all()

            return records, total
        except Exception as e:
            logger.error(f"Error fetching paginated transmissions: {e}")
            raise InternalServerException(
                message="Error retrieving transmission records",
                error_code="EIS_PAGINATION_FAILED",
            )


class EisTransmissionItemRepository(BaseRepository[EisTransmissionItem]):
    """Database repository for per-invoice inquiry result items."""

    def __init__(self, db: AsyncSession = Depends(get_async_db)):
        super().__init__(db, EisTransmissionItem)

    async def bulk_create(
        self, items_data: List[dict], *, commit: bool = True
    ) -> List[EisTransmissionItem]:
        """Bulk insert validation result records returned by BIR inquiry."""
        try:
            created_items: List[EisTransmissionItem] = []
            for data in items_data:
                item = EisTransmissionItem(**data)
                self.db.add(item)
                created_items.append(item)

            if commit:
                await self.db.commit()
            else:
                await self.db.flush()
            return created_items
        except Exception as e:
            logger.error(f"Error bulk creating transmission items: {e}")
            raise InternalServerException(
                message="Error saving transmission item results",
                error_code="EIS_ITEMS_BULK_CREATE_FAILED",
            )

    async def get_by_transmission_id(
        self, transmission_id: uuid.UUID
    ) -> Sequence[EisTransmissionItem]:
        """Fetch all item results for a given transmission batch."""
        try:
            stmt = (
                select(EisTransmissionItem)
                .where(EisTransmissionItem.transmission_id == transmission_id)
                .order_by(EisTransmissionItem.created_at.asc())
            )
            result = await self.db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching items for transmission {transmission_id}: {e}")
            raise InternalServerException(
                message="Error retrieving transmission items",
                error_code="EIS_ITEMS_QUERY_FAILED",
            )
