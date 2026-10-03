from datetime import datetime, timezone
from typing import Optional

from db.db_session import get_async_db
from exceptions.app_exception import InternalServerException
from fastapi import Depends
from loguru import logger
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from base.repository import BaseRepository
from modules.session.session_model import UserSession


class UserSessionRepository(BaseRepository[UserSession]):
    """Repository for user session. Mostly, CRUD operations.

    Using UserSession model.
    """

    def __init__(
            self, 
            db: AsyncSession = Depends(get_async_db)
        ):
        super().__init__(db, UserSession)
        
        
    async def deactivate_token(
        self, refresh_token_hash: str
    ) -> Optional[UserSession]:
        """Deactivates/revokes an active refresh token session and returns the updated record."""
        try:
            stmt = (
                update(UserSession)
                .where(
                    UserSession.refresh_token_hash == refresh_token_hash,
                    UserSession.is_active.is_(True),
                    UserSession.expires_at > datetime.now(timezone.utc),
                )
                .values(is_active=False)
                .returning(UserSession)
            )

            result = await self.db.execute(stmt)
            await self.db.flush()

            # Returns the updated UserSession instance, or None if no match was found/updated
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(
                f"Error deactivating session with token hash {refresh_token_hash}: {e}"
            )
            raise InternalServerException(
                message="Failed to update session status",
                error_code="SESSION_UPDATE_FAILED",
            )     
            