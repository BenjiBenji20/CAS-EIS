from datetime import datetime, date, timedelta, timezone
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.authentication.auth_model import Permission, User, UserStatus
from modules.session.session_model import UserSession
from modules.profile.user_profile_model import UserGender, UserProfile


@pytest.mark.asyncio
async def test_create_permission_persists(db_session: AsyncSession):
    """Verify Permission model persists cleanly to PostgreSQL."""
    unique_id = uuid.uuid4().hex[:8]
    code = f"journal:{unique_id}"
    perm = Permission(
        code=code,
        module="accounting",
        name="Test Post Journal",
        description="Permission for testing",
    )
    db_session.add(perm)
    await db_session.flush()

    assert isinstance(perm.id, uuid.UUID)
    assert isinstance(perm.created_at, datetime)

    retrieved = await db_session.scalar(select(Permission).where(Permission.code == code))
    assert retrieved is not None
    assert retrieved.id == perm.id


@pytest.mark.asyncio
async def test_create_user_with_profile_persists(db_session: AsyncSession):
    """Verify User and UserProfile extension persist cleanly."""
    unique_id = uuid.uuid4().hex[:8]
    user = User(
        username=f"john_{unique_id}",
        email=f"john_{unique_id}@example.com",
        password_hash="hashed_pw_123",
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.flush()

    profile = UserProfile(
        user_id=user.id,
        first_name="John",
        last_name="Doe",
        gender=UserGender.MALE,
        cellphone_number="+639171234567",
        date_of_birth=date(1995, 5, 20),
        country="Philippines",
    )
    db_session.add(profile)
    await db_session.flush()

    assert profile.user_id == user.id
    assert isinstance(profile.created_at, datetime)

    retrieved_user = await db_session.scalar(select(User).where(User.id == user.id))
    assert retrieved_user is not None
    assert retrieved_user.status == UserStatus.ACTIVE


@pytest.mark.asyncio
async def test_create_user_session_persists(db_session: AsyncSession):
    """Verify UserSession persists with correct FK link."""
    unique_id = uuid.uuid4().hex[:8]
    user = User(
        username=f"sess_{unique_id}",
        email=f"sess_{unique_id}@example.com",
        password_hash="hashed_pw_456",
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.flush()

    session_record = UserSession(
        user_id=user.id,
        refresh_token_hash=f"hash_{unique_id}",
        is_active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(session_record)
    await db_session.flush()

    assert isinstance(session_record.id, uuid.UUID)
    assert session_record.user_id == user.id
