from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import Request
from core.settings import settings
from exceptions.app_exception import TooManyRequestsException, UnauthorizedException
from dependencies.rate_limit import rate_limit_by_ip


@pytest.mark.asyncio
async def test_rate_limit_invalid_secret_header():
    """Test that requests with invalid secret header raise UnauthorizedException."""
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"X-Custom-Secret": "invalid_secret"}
    mock_redis = AsyncMock()

    dep = rate_limit_by_ip(max_requests=5, window_sec=60)
    with pytest.raises(UnauthorizedException) as exc_info:
        await dep(request=mock_request, redis=mock_redis)

    assert exc_info.value.status_code == 401
    assert exc_info.value.error_code == "UNAUTHORIZED"
    # Redis should not be called if secret check fails
    mock_redis.incr.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limit_first_request_sets_ttl():
    """Test that the first request within window sets Redis TTL."""
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {settings.SECRET_HEADER_NAME: settings.SECRET_HEADER_VALUE}
    mock_request.client = MagicMock()
    mock_request.client.host = "127.0.0.1"
    mock_request.scope = {"route": MagicMock(path="/api/test")}

    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1

    dep = rate_limit_by_ip(max_requests=5, window_sec=60)
    await dep(request=mock_request, redis=mock_redis)

    mock_redis.incr.assert_awaited_once_with("rate_limit:/api/test:127.0.0.1")
    mock_redis.expire.assert_awaited_once_with("rate_limit:/api/test:127.0.0.1", 60)


@pytest.mark.asyncio
async def test_rate_limit_subsequent_request_does_not_reset_ttl():
    """Test that subsequent requests increment count but do not call expire."""
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {settings.SECRET_HEADER_NAME: settings.SECRET_HEADER_VALUE}
    mock_request.client = MagicMock()
    mock_request.client.host = "192.168.1.1"
    mock_request.scope = {"route": MagicMock(path="/api/test")}

    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 2

    dep = rate_limit_by_ip(max_requests=5, window_sec=60)
    await dep(request=mock_request, redis=mock_redis)

    mock_redis.incr.assert_awaited_once_with("rate_limit:/api/test:192.168.1.1")
    mock_redis.expire.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limit_exceeded_raises_too_many_requests():
    """Test that exceeding max_requests raises TooManyRequestsException."""
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {settings.SECRET_HEADER_NAME: settings.SECRET_HEADER_VALUE}
    mock_request.client = MagicMock()
    mock_request.client.host = "10.0.0.1"
    mock_request.scope = {"route": MagicMock(path="/api/test")}

    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 6
    mock_redis.ttl.return_value = 45

    dep = rate_limit_by_ip(max_requests=5, window_sec=60)
    with pytest.raises(TooManyRequestsException) as exc_info:
        await dep(request=mock_request, redis=mock_redis)

    assert exc_info.value.status_code == 429
    assert exc_info.value.error_code == "RATE_LIMIT_EXCEEDED"
    assert exc_info.value.details == {"retryAfterSeconds": 45}


@pytest.mark.asyncio
async def test_rate_limit_uses_x_forwarded_for_proxy_header():
    """Test that X-Forwarded-For header takes precedence for IP determination."""
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {
        settings.SECRET_HEADER_NAME: settings.SECRET_HEADER_VALUE,
        "X-Forwarded-For": "203.0.113.195, 70.41.3.18, 150.172.238.178"
    }
    mock_request.scope = {"route": MagicMock(path="/api/proxy-test")}

    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1

    dep = rate_limit_by_ip(max_requests=10, window_sec=60)
    await dep(request=mock_request, redis=mock_redis)

    mock_redis.incr.assert_awaited_once_with("rate_limit:/api/proxy-test:203.0.113.195")


@pytest.mark.asyncio
async def test_rate_limit_redis_failure_bypasses_gracefully():
    """Test that Redis connection errors are logged and request is allowed (fail open)."""
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {settings.SECRET_HEADER_NAME: settings.SECRET_HEADER_VALUE}
    mock_request.client = MagicMock()
    mock_request.client.host = "127.0.0.1"
    mock_request.scope = {"route": MagicMock(path="/api/test")}

    mock_redis = AsyncMock()
    mock_redis.incr.side_effect = Exception("Redis connection refused")

    dep = rate_limit_by_ip(max_requests=5, window_sec=60)
    # Should not raise exception
    await dep(request=mock_request, redis=mock_redis)
