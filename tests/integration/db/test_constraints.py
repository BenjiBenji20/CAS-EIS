import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from modules.authentication.auth_model import Permission, Role, User, UserRole


@pytest.mark.asyncio
async def test_duplicate_user_email_raises_integrity_error(db_session: AsyncSession):
    """Verify UNIQUE constraint on auth.users(email) throws IntegrityError."""
    unique_id = uuid.uuid4().hex[:8]
    email = f"dup_{unique_id}@example.com"
    user1 = User(username=f"u1_{unique_id}", email=email, password_hash="pw1")
    user2 = User(username=f"u2_{unique_id}", email=email, password_hash="pw2")

    db_session.add(user1)
    await db_session.flush()

    db_session.add(user2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_duplicate_username_raises_integrity_error(db_session: AsyncSession):
    """Verify UNIQUE constraint on auth.users(username) throws IntegrityError."""
    unique_id = uuid.uuid4().hex[:8]
    username = f"same_{unique_id}"
    user1 = User(username=username, email=f"u1_{unique_id}@example.com", password_hash="pw1")
    user2 = User(username=username, email=f"u2_{unique_id}@example.com", password_hash="pw2")

    db_session.add(user1)
    await db_session.flush()

    db_session.add(user2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_duplicate_permission_code_raises_integrity_error(db_session: AsyncSession):
    """Verify UNIQUE constraint on auth.permissions(code) throws IntegrityError."""
    unique_id = uuid.uuid4().hex[:8]
    code = f"code:{unique_id}"
    p1 = Permission(code=code, module="acct", name="Post Entry 1")
    p2 = Permission(code=code, module="acct", name="Post Entry 2")

    db_session.add(p1)
    await db_session.flush()

    db_session.add(p2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_duplicate_role_name_raises_integrity_error(db_session: AsyncSession):
    """Verify UNIQUE constraint on auth.roles(name) throws IntegrityError."""
    unique_id = uuid.uuid4().hex[:8]
    name = f"Role_{unique_id}"
    r1 = Role(name=name, description="Role 1")
    r2 = Role(name=name, description="Role 2")

    db_session.add(r1)
    await db_session.flush()

    db_session.add(r2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_invalid_foreign_key_user_role_raises_integrity_error(db_session: AsyncSession):
    """Verify inserting non-existent user_id into auth.user_roles throws IntegrityError."""
    user_role = UserRole(user_id=uuid.uuid4(), role_id=uuid.uuid4())
    db_session.add(user_role)

    with pytest.raises(IntegrityError):
        await db_session.flush()
