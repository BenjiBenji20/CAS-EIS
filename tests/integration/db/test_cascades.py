from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.authentication.auth_model import Permission, Role, RolePermission, User, UserRole
from modules.session.session_model import UserSession
from modules.profile.user_profile_model import UserGender, UserProfile


@pytest.mark.asyncio
async def test_delete_user_cascades_profile_and_sessions(db_session: AsyncSession):
    """Verify deleting a User automatically CASCADE deletes UserProfile and UserSession records in real PostgreSQL."""
    unique_id = uuid.uuid4().hex[:8]
    user = User(
        username=f"del_{unique_id}",
        email=f"del_{unique_id}@example.com",
        password_hash="pw"
    )
    db_session.add(user)
    await db_session.flush()

    profile = UserProfile(
        user_id=user.id,
        first_name="Delete",
        last_name="Target",
        gender=UserGender.MALE,
        cellphone_number="+639170000000",
    )
    session = UserSession(
        user_id=user.id,
        refresh_token_hash=f"hash_del_{unique_id}",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add_all([profile, session])
    await db_session.flush()

    # Delete parent User
    await db_session.delete(user)
    await db_session.flush()

    # Verify UserProfile is deleted by CASCADE
    del_profile = await db_session.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    assert del_profile is None

    # Verify UserSession is deleted by CASCADE
    del_session = await db_session.scalar(select(UserSession).where(UserSession.user_id == user.id))
    assert del_session is None


@pytest.mark.asyncio
async def test_delete_user_cascades_user_roles(db_session: AsyncSession):
    """Verify deleting a User removes entries in auth.user_roles junction table, leaving Role intact."""
    unique_id = uuid.uuid4().hex[:8]
    role = Role(name=f"Test Role {unique_id}", description="Test Role")
    db_session.add(role)
    await db_session.flush()

    user = User(username=f"role_del_{unique_id}", email=f"userdel_{unique_id}@example.com", password_hash="pw", roles=[role])
    db_session.add(user)
    await db_session.flush()

    await db_session.delete(user)
    await db_session.flush()

    # Verify junction table entry is deleted
    link = await db_session.scalar(select(UserRole).where(UserRole.user_id == user.id))
    assert link is None

    # Verify Role itself remains intact
    surviving_role = await db_session.scalar(select(Role).where(Role.id == role.id))
    assert surviving_role is not None


@pytest.mark.asyncio
async def test_delete_role_cascades_role_permissions(db_session: AsyncSession):
    """Verify deleting a Role removes entries in auth.role_permissions junction table, leaving Permission intact."""
    unique_id = uuid.uuid4().hex[:8]
    perm = Permission(code=f"perm_{unique_id}", module="temp", name="Temp Perm")
    db_session.add(perm)
    await db_session.flush()

    role = Role(name=f"Role Delete {unique_id}", permissions=[perm])
    db_session.add(role)
    await db_session.flush()

    await db_session.delete(role)
    await db_session.flush()

    # Verify junction table entry is deleted
    link = await db_session.scalar(select(RolePermission).where(RolePermission.role_id == role.id))
    assert link is None

    # Verify Permission itself remains intact
    surviving_perm = await db_session.scalar(select(Permission).where(Permission.id == perm.id))
    assert surviving_perm is not None
