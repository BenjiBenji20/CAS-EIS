import uuid
import pytest
from modules.authentication.auth_model import User, UserStatus
from modules.authentication.auth_repository import AuthenticationRepository
from modules.authentication.auth_service import AuthenticationService

pwd_context = AuthenticationService.pwd_context


@pytest.mark.asyncio
async def test_auth_repository_is_email_exists(db_session):
    """Integration test checking is_email_exists against real PostgreSQL database."""
    repo = AuthenticationRepository(db=db_session)
    unique_id = uuid.uuid4().hex[:8]
    test_email = f"auth_repo_{unique_id}@example.com"
    test_username = f"usr_{unique_id}"

    # Initially email should not exist
    exists_before = await repo.is_email_exists(test_email)
    assert exists_before is False

    # Insert user into database
    user_data = {
        "username": test_username,
        "email": test_email,
        "password_hash": pwd_context.hash("SecurePass123!"),
        "status": UserStatus.PENDING,
    }
    created_user = await repo.create(data=user_data, commit=False)
    assert created_user.id is not None

    # Verify is_email_exists returns True
    exists_after = await repo.is_email_exists(test_email)
    assert exists_after is True


@pytest.mark.asyncio
async def test_auth_repository_get_by_id(db_session):
    """Integration test creating and fetching user via BaseRepository get_by_id method."""
    repo = AuthenticationRepository(db=db_session)
    unique_id = uuid.uuid4().hex[:8]
    test_email = f"fetch_{unique_id}@example.com"
    test_username = f"usr_fetch_{unique_id}"

    user_data = {
        "username": test_username,
        "email": test_email,
        "password_hash": pwd_context.hash("SecurePass123!"),
        "status": UserStatus.PENDING,
    }
    created_user = await repo.create(data=user_data, commit=False)

    fetched_user = await repo.get_by_id(created_user.id)
    assert fetched_user is not None
    assert fetched_user.username == test_username
    assert fetched_user.email == test_email
