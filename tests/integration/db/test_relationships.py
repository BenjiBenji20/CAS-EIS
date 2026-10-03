from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.authentication.auth_model import Permission, Role, User
from modules.session.session_model import UserSession
from modules.profile.user_profile_model import UserGender, UserProfile


@pytest.mark.asyncio
async def test_role_permission_many_to_many_relationship(db_session: AsyncSession):
    """Verify Many-to-Many association between Role and Permission works bi-directionally."""
    unique_id = uuid.uuid4().hex[:8]
    p1 = Permission(code=f"sales:create:{unique_id}", module="sales", name="Create Sales Order")
    p2 = Permission(code=f"sales:approve:{unique_id}", module="sales", name="Approve Sales Order")
    db_session.add_all([p1, p2])
    await db_session.flush()

    role = Role(name=f"Sales Manager {unique_id}", description="Manages sales orders", permissions=[p1, p2])
    db_session.add(role)
    await db_session.flush()

    target_role_id = role.id
    db_session.expire_all()

    fetched_role = await db_session.scalar(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == target_role_id)
    )
    assert fetched_role is not None
    assert len(fetched_role.permissions) == 2
    codes = [p.code for p in fetched_role.permissions]
    assert f"sales:create:{unique_id}" in codes
    assert f"sales:approve:{unique_id}" in codes


@pytest.mark.asyncio
async def test_user_role_many_to_many_relationship(db_session: AsyncSession):
    """Verify Many-to-Many association between User and Role works bi-directionally."""
    unique_id = uuid.uuid4().hex[:8]
    r1 = Role(name=f"Encoder {unique_id}", description="Data Encoder")
    r2 = Role(name=f"Viewer {unique_id}", description="Read-only Viewer")
    db_session.add_all([r1, r2])
    await db_session.flush()

    user = User(username=f"multi_{unique_id}", email=f"multi_{unique_id}@example.com", password_hash="pw", roles=[r1, r2])
    db_session.add(user)
    await db_session.flush()

    target_user_id = user.id
    db_session.expire_all()

    fetched_user = await db_session.scalar(
        select(User).options(selectinload(User.roles)).where(User.id == target_user_id)
    )
    assert fetched_user is not None
    assert len(fetched_user.roles) == 2
    role_names = [r.name for r in fetched_user.roles]
    assert f"Encoder {unique_id}" in role_names
    assert f"Viewer {unique_id}" in role_names


@pytest.mark.asyncio
async def test_user_one_to_one_profile_relationship(db_session: AsyncSession):
    """Verify One-to-One 1:1 bidirectional navigation between User and UserProfile."""
    unique_id = uuid.uuid4().hex[:8]
    user = User(username=f"owner_{unique_id}", email=f"owner_{unique_id}@example.com", password_hash="pw")
    db_session.add(user)
    await db_session.flush()

    profile = UserProfile(
        user_id=user.id,
        first_name="Jane",
        last_name="Smith",
        gender=UserGender.FEMALE,
        cellphone_number="+639181112222",
    )
    db_session.add(profile)
    await db_session.flush()

    target_user_id = user.id
    db_session.expire_all()

    fetched_user = await db_session.scalar(
        select(User).options(selectinload(User.profile)).where(User.id == target_user_id)
    )
    assert fetched_user is not None
    assert fetched_user.profile is not None
    assert fetched_user.profile.first_name == "Jane"

    fetched_profile = await db_session.scalar(
        select(UserProfile).options(selectinload(UserProfile.user)).where(UserProfile.user_id == target_user_id)
    )
    assert fetched_profile is not None
    assert fetched_profile.user.username == f"owner_{unique_id}"


@pytest.mark.asyncio
async def test_user_one_to_many_sessions_relationship(db_session: AsyncSession):
    """Verify One-to-Many 1:N navigation between User and UserSession."""
    unique_id = uuid.uuid4().hex[:8]
    user = User(username=f"act_{unique_id}", email=f"act_{unique_id}@example.com", password_hash="pw")
    db_session.add(user)
    await db_session.flush()

    s1 = UserSession(user_id=user.id, refresh_token_hash=f"hash_1_{unique_id}", expires_at=datetime.now(timezone.utc) + timedelta(days=1))
    s2 = UserSession(user_id=user.id, refresh_token_hash=f"hash_2_{unique_id}", expires_at=datetime.now(timezone.utc) + timedelta(days=2))
    db_session.add_all([s1, s2])
    await db_session.flush()

    target_user_id = user.id
    db_session.expire_all()

    fetched_user = await db_session.scalar(
        select(User).options(selectinload(User.sessions)).where(User.id == target_user_id)
    )
    assert fetched_user is not None
    assert len(fetched_user.sessions) == 2
