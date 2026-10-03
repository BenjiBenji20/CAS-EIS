from typing import Optional

from db.db_session import get_async_db
from fastapi import Depends
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from base.repository import BaseRepository
from modules.authentication.auth_model import User
from exceptions.app_exception import InternalServerException


class AuthenticationRepository(BaseRepository[User]):
    """Repository for authentication operations.

    Using User model.
    """

    def __init__(
            self, 
            db: AsyncSession = Depends(get_async_db)
        ):
        super().__init__(db, User)
        
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Searcu user by username. Limit search by 1 only."""
        try:
            query = select(User).where(User.username == username).limit(1)
            result = await self.db.execute(query)
            return result.scalars().first()
        except Exception as e:
            logger.error(f"Error occurred while searching for username {username}: {e}")
            raise InternalServerException(
                message="Error occurred while searching for username.",
                error_code="USER_VALIDATION_FAILED"
            )


    async def is_email_exists(self, email: str) -> bool:
        """Check if email is already registered in the table."""
        try:
            stmt = select(exists().where(User.email == email))
            result = await self.db.execute(stmt)
            return bool(result.scalar())
        except Exception as e:
            logger.error(f"Error occurred while searching for email {email}: {e}")
            raise InternalServerException(
                message="Failed to perform user validation check",
                error_code="USER_VALIDATION_FAILED"
            )

