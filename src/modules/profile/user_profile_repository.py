from db.db_session import get_async_db
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from base.repository import BaseRepository
from modules.profile.user_profile_model import UserProfile


class UserProfileRepository(BaseRepository[UserProfile]):
    """Repository for user profile. Mostly, CRUD operations.

    Using UserProfile model.
    """

    def __init__(
            self, 
            db: AsyncSession = Depends(get_async_db)
        ):
        super().__init__(db, UserProfile)
        