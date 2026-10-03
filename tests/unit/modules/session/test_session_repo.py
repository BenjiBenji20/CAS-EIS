from unittest.mock import AsyncMock, MagicMock
import pytest
from exceptions.app_exception import InternalServerException
from modules.session.session_repo import UserSessionRepository


@pytest.mark.asyncio
async def test_deactivate_token_success():
    """Test successful deactivation of an active session token."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_session_instance = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_session_instance
    mock_db.execute.return_value = mock_result

    repo = UserSessionRepository(db=mock_db)
    result = await repo.deactivate_token("sample_token_hash_123")

    mock_db.execute.assert_awaited_once()
    mock_db.flush.assert_awaited_once()
    assert result == mock_session_instance


@pytest.mark.asyncio
async def test_deactivate_token_not_found_returns_none():
    """Test deactivating non-existent or already expired token returns None."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    repo = UserSessionRepository(db=mock_db)
    result = await repo.deactivate_token("non_existent_hash")

    assert result is None


@pytest.mark.asyncio
async def test_deactivate_token_db_exception_raises_internal_server_exception():
    """Test that DB exceptions during session update raise InternalServerException."""
    mock_db = AsyncMock()
    mock_db.execute.side_effect = Exception("DB query timeout")

    repo = UserSessionRepository(db=mock_db)
    with pytest.raises(InternalServerException) as exc_info:
        await repo.deactivate_token("error_hash")

    assert exc_info.value.status_code == 500
    assert exc_info.value.error_code == "SESSION_UPDATE_FAILED"
