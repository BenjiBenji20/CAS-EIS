from unittest.mock import AsyncMock
import pytest
from core.settings import settings
from utils.maintain_cache_key import MaintainCacheKeyUtils


def test_get_profile_completion_key():
    """Test generating standardized profile completion cache key."""
    utils = MaintainCacheKeyUtils(async_cache=AsyncMock())
    key = utils.get_profile_completion_key("123e4567-e89b-12d3-a456-426614174000")
    assert key == "user:profile_completed:123e4567-e89b-12d3-a456-426614174000"


def test_get_failed_login_keys():
    """Test generating failed login count and block keys."""
    utils = MaintainCacheKeyUtils(async_cache=AsyncMock())
    assert utils.get_failed_login_count_key("127.0.0.1", "john") == "failed_login_count:127.0.0.1:john"
    assert utils.get_failed_login_block_key("127.0.0.1", "john") == "failed_login_block:127.0.0.1:john"


@pytest.mark.asyncio
async def test_profile_completion_cache_completed_true():
    """Test caching profile completion status = True in Redis."""
    mock_redis = AsyncMock()
    utils = MaintainCacheKeyUtils(async_cache=mock_redis)

    await utils.profile_completion_cache("user-123", is_profile_completed=True)

    mock_redis.set.assert_awaited_once_with(
        name="user:profile_completed:user-123",
        value="1",
        ex=settings.REFRESH_JWT_EXPIRY_SEC
    )


@pytest.mark.asyncio
async def test_profile_completion_cache_completed_false():
    """Test caching profile completion status = False in Redis."""
    mock_redis = AsyncMock()
    utils = MaintainCacheKeyUtils(async_cache=mock_redis)

    await utils.profile_completion_cache("user-456", is_profile_completed=False)

    mock_redis.set.assert_awaited_once_with(
        name="user:profile_completed:user-456",
        value="0",
        ex=settings.REFRESH_JWT_EXPIRY_SEC
    )


@pytest.mark.asyncio
async def test_profile_completion_cache_redis_error_handled_gracefully():
    """Test that Redis exceptions during caching do not bubble up or break execution."""
    mock_redis = AsyncMock()
    mock_redis.set.side_effect = Exception("Redis network timeout")
    utils = MaintainCacheKeyUtils(async_cache=mock_redis)

    # Should log warning and complete without raising
    await utils.profile_completion_cache("user-789", is_profile_completed=True)


@pytest.mark.asyncio
async def test_record_failed_login_first_attempt():
    """Test recording first failed login attempt sets TTL and returns False."""
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1
    utils = MaintainCacheKeyUtils(async_cache=mock_redis)

    is_blocked = await utils.record_failed_login(ip="192.168.1.1", username="testuser")

    assert is_blocked is False
    mock_redis.incr.assert_awaited_once_with("failed_login_count:192.168.1.1:testuser")
    mock_redis.expire.assert_awaited_once_with("failed_login_count:192.168.1.1:testuser", 900)


@pytest.mark.asyncio
async def test_record_failed_login_lockout_threshold():
    """Test reaching 5th failed attempt sets lockout block key and returns True."""
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 5
    utils = MaintainCacheKeyUtils(async_cache=mock_redis)

    is_blocked = await utils.record_failed_login(ip="192.168.1.1", username="testuser")

    assert is_blocked is True
    mock_redis.set.assert_awaited_once_with(
        name="failed_login_block:192.168.1.1:testuser",
        value="1",
        ex=900
    )


@pytest.mark.asyncio
async def test_clear_failed_login():
    """Test clear_failed_login deletes counter and block keys in Redis."""
    mock_redis = AsyncMock()
    utils = MaintainCacheKeyUtils(async_cache=mock_redis)

    await utils.clear_failed_login(ip="10.0.0.1", username="alice")

    mock_redis.delete.assert_awaited_once_with(
        "failed_login_count:10.0.0.1:alice",
        "failed_login_block:10.0.0.1:alice"
    )


@pytest.mark.asyncio
async def test_is_ip_user_blocked_returns_true_when_blocked():
    """Test is_ip_user_blocked returns True if block key exists in Redis."""
    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 1
    utils = MaintainCacheKeyUtils(async_cache=mock_redis)

    result = await utils.is_ip_user_blocked(ip="10.0.0.1", username="alice")

    assert result is True
    mock_redis.exists.assert_awaited_once_with("failed_login_block:10.0.0.1:alice")


@pytest.mark.asyncio
async def test_is_ip_user_blocked_returns_false_when_not_blocked():
    """Test is_ip_user_blocked returns False if block key does not exist."""
    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0
    utils = MaintainCacheKeyUtils(async_cache=mock_redis)

    result = await utils.is_ip_user_blocked(ip="10.0.0.1", username="bob")

    assert result is False


@pytest.mark.asyncio
async def test_admin_unblock_user():
    """Test admin_unblock_user scans and deletes all block and count keys for a user."""
    mock_redis = AsyncMock()

    async def mock_scan_iter(pattern):
        if "failed_login_block" in pattern:
            yield "failed_login_block:192.168.1.1:victim"
        elif "failed_login_count" in pattern:
            yield "failed_login_count:192.168.1.1:victim"

    mock_redis.scan_iter = mock_scan_iter
    utils = MaintainCacheKeyUtils(async_cache=mock_redis)

    await utils.admin_unblock_user("victim")

    mock_redis.delete.assert_any_await("failed_login_block:192.168.1.1:victim")
    mock_redis.delete.assert_any_await("failed_login_count:192.168.1.1:victim")
