from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest

from exceptions.app_exception import BadRequestException, NotFoundException
from modules.authentication.auth_model import Permission, Role, User
from modules.rbac.rbac_schema import (
    BatchRolePermissionAssignmentPayload,
    RoleAssignmentItem,
)
from modules.rbac.rbac_service import RBACService
from shares.enums import RoleName, SystemPermission


@pytest.fixture
def mock_rbac_repo():
    repo = MagicMock()
    repo.db = MagicMock()
    repo.db.commit = AsyncMock()
    return repo


@pytest.fixture
def mock_auth_repo():
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_cache_utils():
    utils = MagicMock()
    utils.async_cache = MagicMock()
    utils.async_cache.get = AsyncMock(return_value=None)
    utils.create_user_permission_cache_key = MagicMock(side_effect=lambda uid: f"user_permission:{uid}")
    utils.cache_user_permissions = AsyncMock()
    utils.invalidate_user_permission_cache = AsyncMock()
    return utils


@pytest.fixture
def rbac_service(mock_rbac_repo, mock_auth_repo, mock_cache_utils):
    return RBACService(rbac_repo=mock_rbac_repo, auth_repo=mock_auth_repo, cache_utils=mock_cache_utils)


@pytest.mark.asyncio
async def test_get_rbac_configuration(rbac_service, mock_rbac_repo):
    """Test get_rbac_configuration returns hierarchical tree and active roles with permissions."""
    role_id = uuid.uuid4()
    mock_perm = MagicMock(spec=Permission)
    mock_perm.code = SystemPermission.AUTHENTICATION_USER_READ.value

    mock_role = MagicMock(spec=Role)
    mock_role.id = role_id
    mock_role.name = "ADMIN"
    mock_role.description = "System Administrator"
    mock_role.is_system_role = True
    mock_role.permissions = [mock_perm]

    mock_rbac_repo.get_all_roles = AsyncMock(return_value=[mock_role])

    config = await rbac_service.get_rbac_configuration()

    # Verify modules structure
    module_names = [m.name for m in config.modules]
    assert "AUTHENTICATION" in module_names
    assert "PROFILE" in module_names
    assert "RBAC" in module_names

    auth_mod = next(m for m in config.modules if m.name == "AUTHENTICATION")
    res_names = [r.name for r in auth_mod.resources]
    assert "REGISTRATION" in res_names
    assert "USER" in res_names

    reg_res = next(r for r in auth_mod.resources if r.name == "REGISTRATION")
    act_names = [a.name for a in reg_res.actions]
    assert "ACCEPT" in act_names
    accept_act = next(a for a in reg_res.actions if a.name == "ACCEPT")
    assert accept_act.permission == "AUTHENTICATION:REGISTRATION:ACCEPT"

    # Verify roles structure
    assert len(config.roles) == 1
    assert config.roles[0].name == "ADMIN"
    assert config.roles[0].permissions == [SystemPermission.AUTHENTICATION_USER_READ.value]


@pytest.mark.asyncio
async def test_get_or_cache_user_permissions_cache_hit(rbac_service, mock_cache_utils):
    """Test returning cached user permissions directly from Redis."""
    user_id = uuid.uuid4()
    mock_cache_utils.async_cache.get = AsyncMock(
        return_value='{"user_id": "' + str(user_id) + '", "roles": ["ADMIN"], "permissions": ["RBAC:ROLE:READ"]}'
    )

    result = await rbac_service.get_or_cache_user_permissions(user_id)
    assert result.user_id == user_id
    assert result.roles == ["ADMIN"]
    assert result.permissions == ["RBAC:ROLE:READ"]
    mock_cache_utils.cache_user_permissions.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_cache_user_permissions_cache_miss(rbac_service, mock_rbac_repo, mock_cache_utils):
    """Test querying DB on cache miss and warming Redis cache."""
    user_id = uuid.uuid4()
    mock_cache_utils.async_cache.get = AsyncMock(return_value=None)
    mock_rbac_repo.get_user_roles_and_permissions = AsyncMock(
        return_value={
            "user_id": str(user_id),
            "roles": ["STAFF_USER"],
            "permissions": ["PROFILE:USER:READ", "PROFILE:USER:UPDATE"],
        }
    )

    result = await rbac_service.get_or_cache_user_permissions(user_id)
    assert result.user_id == user_id
    assert result.roles == ["STAFF_USER"]
    assert "PROFILE:USER:READ" in result.permissions
    mock_cache_utils.cache_user_permissions.assert_awaited_once_with(
        str(user_id),
        {
            "user_id": str(user_id),
            "roles": ["STAFF_USER"],
            "permissions": ["PROFILE:USER:READ", "PROFILE:USER:UPDATE"],
        }
    )


@pytest.mark.asyncio
async def test_invalidate_user_permissions(rbac_service, mock_cache_utils):
    """Test cache invalidation forwards correctly to MaintainCacheKeyUtils."""
    user_id = uuid.uuid4()
    await rbac_service.invalidate_user_permissions(user_id)
    mock_cache_utils.invalidate_user_permission_cache.assert_awaited_once_with(str(user_id))


@pytest.mark.asyncio
async def test_get_user_rbac_summary_success(rbac_service, mock_rbac_repo, mock_auth_repo, mock_cache_utils):
    """Test retrieving user RBAC summary when user exists."""
    user_id = uuid.uuid4()
    mock_user = MagicMock(spec=User)
    mock_user.id = user_id
    mock_user.user_code = "USR-00005"
    mock_user.username = "staffuser"
    mock_auth_repo.get_by_id = AsyncMock(return_value=mock_user)

    mock_rbac_repo.get_user_roles_and_permissions = AsyncMock(
        return_value={
            "user_id": str(user_id),
            "roles": ["STAFF_USER"],
            "permissions": ["PROFILE:USER:READ"],
        }
    )

    summary = await rbac_service.get_user_rbac_summary(user_id)
    assert summary.user_id == user_id
    assert summary.user_code == "USR-00005"
    assert summary.username == "staffuser"
    assert summary.roles == ["STAFF_USER"]


@pytest.mark.asyncio
async def test_get_user_rbac_summary_not_found(rbac_service, mock_auth_repo):
    """Test NotFoundException when user does not exist."""
    user_id = uuid.uuid4()
    mock_auth_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException):
        await rbac_service.get_user_rbac_summary(user_id)


@pytest.mark.asyncio
async def test_assign_roles_to_user_success(rbac_service, mock_rbac_repo, mock_auth_repo, mock_cache_utils):
    """Test assigning roles by role name to user and flushing cache."""
    user_id = uuid.uuid4()
    role_id_1 = uuid.uuid4()
    mock_user = MagicMock(spec=User)
    mock_user.id = user_id
    mock_user.username = "testuser"
    mock_auth_repo.get_by_id = AsyncMock(return_value=mock_user)

    mock_role = MagicMock(spec=Role)
    mock_role.id = role_id_1
    mock_role.name = "ADMIN"
    mock_rbac_repo.resolve_roles = AsyncMock(return_value=[mock_role])
    mock_rbac_repo.assign_roles_to_user = AsyncMock(return_value=["ADMIN"])

    res = await rbac_service.assign_roles_to_user(user_id, ["ADMIN"])
    assert res.status is True
    assert res.assigned_roles == ["ADMIN"]
    mock_rbac_repo.db.commit.assert_awaited_once()
    mock_cache_utils.invalidate_user_permission_cache.assert_awaited_once_with(str(user_id))


@pytest.mark.asyncio
async def test_assign_roles_to_user_invalid_role(rbac_service, mock_rbac_repo, mock_auth_repo):
    """Test BadRequestException when non-existent role name is provided."""
    user_id = uuid.uuid4()
    mock_user = MagicMock(spec=User)
    mock_auth_repo.get_by_id = AsyncMock(return_value=mock_user)
    mock_rbac_repo.resolve_roles = AsyncMock(return_value=[])

    with pytest.raises(BadRequestException):
        await rbac_service.assign_roles_to_user(user_id, ["NON_EXISTENT_ROLE"])


@pytest.mark.asyncio
async def test_assign_permissions_to_role_success(rbac_service, mock_rbac_repo, mock_cache_utils):
    """Test assigning permissions to role by permission code and invalidating affected users."""
    role_id = uuid.uuid4()
    perm_id_1 = uuid.uuid4()
    mock_role = MagicMock(spec=Role)
    mock_role.id = role_id
    mock_role.name = "ADMIN"
    mock_rbac_repo.get_role_by_identifier = AsyncMock(return_value=mock_role)

    mock_perm = MagicMock(spec=Permission)
    mock_perm.id = perm_id_1
    mock_perm.code = "AUTHENTICATION:USER:READ"
    mock_rbac_repo.resolve_permissions = AsyncMock(return_value=[mock_perm])
    mock_rbac_repo.assign_permissions_to_role = AsyncMock(return_value=["AUTHENTICATION:USER:READ"])

    affected_user_id = uuid.uuid4()
    mock_rbac_repo.get_user_ids_by_role = AsyncMock(return_value=[affected_user_id])

    res = await rbac_service.assign_permissions_to_role("ADMIN", ["AUTHENTICATION:USER:READ"])
    assert res.status is True
    assert res.role_name == "ADMIN"
    assert res.assigned_permissions == ["AUTHENTICATION:USER:READ"]
    mock_rbac_repo.db.commit.assert_awaited_once()
    mock_cache_utils.invalidate_user_permission_cache.assert_awaited_once_with(str(affected_user_id))


@pytest.mark.asyncio
async def test_batch_assign_role_permissions(rbac_service, mock_rbac_repo, mock_cache_utils):
    """Test batch assigning permissions across multiple roles."""
    role_id_1 = uuid.uuid4()
    mock_role = MagicMock(spec=Role)
    mock_role.id = role_id_1
    mock_role.name = "STAFF_USER"
    mock_rbac_repo.get_role_by_identifier = AsyncMock(return_value=mock_role)

    mock_perm = MagicMock(spec=Permission)
    mock_perm.id = uuid.uuid4()
    mock_perm.code = "PROFILE:USER:READ"
    mock_rbac_repo.resolve_permissions = AsyncMock(return_value=[mock_perm])
    mock_rbac_repo.assign_permissions_to_role = AsyncMock(return_value=["PROFILE:USER:READ"])
    mock_rbac_repo.get_user_ids_by_role = AsyncMock(return_value=[uuid.uuid4()])

    payload = BatchRolePermissionAssignmentPayload(
        assignments=[
            RoleAssignmentItem(role="STAFF_USER", permissions=["PROFILE:USER:READ"])
        ]
    )

    res = await rbac_service.batch_assign_role_permissions(payload)
    assert res.status is True
    assert "STAFF_USER" in res.updated_roles
    mock_rbac_repo.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_role_to_defaults(rbac_service, mock_rbac_repo, mock_cache_utils):
    """Test resetting role to defaults uses ROLE_DEFAULT_PERMISSIONS."""
    role_id = uuid.uuid4()
    mock_role = MagicMock(spec=Role)
    mock_role.id = role_id
    mock_role.name = RoleName.STAFF_USER.value
    mock_rbac_repo.get_role_by_identifier = AsyncMock(return_value=mock_role)

    mock_perm_1 = MagicMock(spec=Permission, id=uuid.uuid4(), code="PROFILE:USER:READ")
    mock_perm_2 = MagicMock(spec=Permission, id=uuid.uuid4(), code="PROFILE:USER:UPDATE")
    mock_rbac_repo.resolve_permissions = AsyncMock(return_value=[mock_perm_1, mock_perm_2])
    mock_rbac_repo.assign_permissions_to_role = AsyncMock(return_value=["PROFILE:USER:READ", "PROFILE:USER:UPDATE"])
    mock_rbac_repo.get_user_ids_by_role = AsyncMock(return_value=[])

    res = await rbac_service.reset_role_to_defaults(RoleName.STAFF_USER.value)
    assert res.status is True
    assert res.role_name == "STAFF_USER"
