import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from base.repository import BaseRepository
from modules.authentication.auth_model import Permission


@pytest.mark.asyncio
async def test_base_repository_crud_lifecycle(db_session: AsyncSession):
    """Verify BaseRepository CRUD operations function correctly on real PostgreSQL test DB."""
    repo = BaseRepository(db_session, Permission)

    unique_id = uuid.uuid4().hex[:8]
    perm_code = f"perm:{unique_id}"

    perm_data = {
        "code": perm_code,
        "module": "testing",
        "name": "Repo CRUD Test Permission",
        "description": "Integration test for BaseRepository",
    }

    # 1. Create (commit=False stays within transaction block)
    obj = await repo.create(perm_data, commit=False)
    assert obj.id is not None
    assert isinstance(obj.id, uuid.UUID)
    assert obj.code == perm_code

    # 2. Get by ID
    fetched = await repo.get_by_id(obj.id)
    assert fetched is not None
    assert fetched.id == obj.id
    assert fetched.code == perm_code

    # 3. Update
    updated_data = {"name": "Updated Repo CRUD Test"}
    updated = await repo.update(fetched, updated_data, commit=False)
    assert updated.name == "Updated Repo CRUD Test"

    # 4. Get by IDs
    fetched_list = await repo.get_by_ids([obj.id])
    assert len(fetched_list) == 1
    assert fetched_list[0].id == obj.id

    # 5. Delete
    await repo.delete(obj, commit=False)
    deleted_check = await repo.get_by_id(obj.id)
    assert deleted_check is None
