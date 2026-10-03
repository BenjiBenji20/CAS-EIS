from datetime import datetime, timedelta, timezone
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import jwt
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from core.settings import settings
from middlewares.jwt_validator import JWTValidator


def create_test_app():
    """Create a lightweight FastAPI app wrapped with JWTValidator middleware."""
    app = FastAPI()
    app.add_middleware(JWTValidator)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.post("/api/public/auth/registration")
    async def public_route():
        return {"message": "public ok"}

    @app.get("/api/private/resource")
    async def private_route(request: Request):
        return {
            "message": "private ok",
            "user_id": str(request.state.user_id),
            "session_id": str(request.state.session_id),
            "user_status": request.state.user_status,
        }

    return app


def generate_test_jwt(user_id: str, session_id: str, token_type: str = "access-token", expired: bool = False, key: str = settings.ACCESS_JWT_SECRET_KEY) -> str:
    """Helper to construct signed test JWTs."""
    now = datetime.now(timezone.utc)
    exp = (now - timedelta(hours=1)) if expired else (now + timedelta(hours=1))
    payload = {
        "sub": user_id,
        "sid": session_id,
        "type": token_type,
        "exp": int(exp.timestamp())
    }
    return jwt.encode(payload, key, algorithm=settings.JWT_ALGORITHM)


@pytest.mark.asyncio
async def test_jwt_validator_public_route_bypass():
    """Verify public routes (/health and /api/public/*) bypass JWT validation without tokens."""
    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res1 = await client.get("/health")
        assert res1.status_code == 200
        assert res1.json()["status"] == "healthy"

        res2 = await client.post("/api/public/auth/registration")
        assert res2.status_code == 200
        assert res2.json()["message"] == "public ok"


@pytest.mark.asyncio
async def test_jwt_validator_missing_token_returns_401():
    """Verify private route request without access token returns 401 Unauthorized."""
    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/private/resource")
        assert res.status_code == 401
        data = res.json()
        assert data["error"]["code"] == "UNAUTHORIZED"
        assert "Authentication required" in data["description"]


@pytest.mark.asyncio
async def test_jwt_validator_expired_token_returns_401():
    """Verify expired access token returns 401 Unauthorized."""
    app = create_test_app()
    token = generate_test_jwt(str(uuid.uuid4()), str(uuid.uuid4()), expired=True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/private/resource",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 401
        assert "Session expired" in res.json()["description"]


@pytest.mark.asyncio
async def test_jwt_validator_invalid_signature_returns_401():
    """Verify tampered JWT signature returns 401 Unauthorized."""
    app = create_test_app()
    token = generate_test_jwt(str(uuid.uuid4()), str(uuid.uuid4()), key="wrong_key_12345678901234567890123456789012")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/private/resource",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 401
        assert "Invalid authentication key" in res.json()["description"]


@pytest.mark.asyncio
async def test_jwt_validator_invalid_token_type_returns_401():
    """Verify refresh-token provided on private route returns 401 Unauthorized."""
    app = create_test_app()
    token = generate_test_jwt(str(uuid.uuid4()), str(uuid.uuid4()), token_type="refresh-token")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/private/resource",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 401
        assert "Unauthorized access" in res.json()["description"]


@pytest.mark.asyncio
async def test_jwt_validator_missing_sub_or_sid_returns_401():
    """Verify token missing sub or sid claims returns 401 Unauthorized."""
    app = create_test_app()
    payload = {"type": "access-token", "exp": 9999999999}
    token = jwt.encode(payload, settings.ACCESS_JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/private/resource",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 401
        assert "Failed authentication" in res.json()["description"]


@pytest.mark.asyncio
@patch("middlewares.jwt_validator.redis_async_client")
async def test_jwt_validator_session_missing_in_redis_returns_401(mock_redis_client):
    """Verify revoked or missing session in Redis returns 401 Unauthorized."""
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    token = generate_test_jwt(user_id, session_id)

    mock_cache = AsyncMock()
    mock_cache.get.return_value = None  # Cache miss / session revoked
    mock_redis_client.redis = mock_cache

    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/private/resource",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 401
        assert "Session has expired or been revoked" in res.json()["description"]


@pytest.mark.asyncio
@patch("middlewares.jwt_validator.redis_async_client")
async def test_jwt_validator_inactive_session_in_redis_returns_401(mock_redis_client):
    """Verify session marked is_active=False in Redis returns 401 Unauthorized."""
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    token = generate_test_jwt(user_id, session_id)

    cached_payload = {
        "id": session_id,
        "user_id": user_id,
        "is_active": False,
        "user_status": "ACTIVE"
    }

    mock_cache = AsyncMock()
    mock_cache.get.return_value = json.dumps(cached_payload)
    mock_redis_client.redis = mock_cache

    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/private/resource",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 401
        assert "Session is inactive" in res.json()["description"]


@pytest.mark.asyncio
@patch("middlewares.jwt_validator.redis_async_client")
async def test_jwt_validator_suspended_user_status_returns_403(mock_redis_client):
    """Verify user account with user_status != ACTIVE in Redis returns 403 Forbidden."""
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    token = generate_test_jwt(user_id, session_id)

    cached_payload = {
        "id": session_id,
        "user_id": user_id,
        "is_active": True,
        "user_status": "SUSPENDED"
    }

    mock_cache = AsyncMock()
    mock_cache.get.return_value = json.dumps(cached_payload)
    mock_redis_client.redis = mock_cache

    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/private/resource",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 403
        assert "FORBIDDEN" == res.json()["error"]["code"]


@pytest.mark.asyncio
@patch("middlewares.jwt_validator.redis_async_client")
async def test_jwt_validator_access_token_hash_mismatch_returns_401(mock_redis_client):
    """Verify rotated access token with hash mismatch in Redis returns 401 Unauthorized."""
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    token = generate_test_jwt(user_id, session_id)

    cached_payload = {
        "id": session_id,
        "user_id": user_id,
        "is_active": True,
        "user_status": "ACTIVE",
        "access_token_hash": "different_rotated_hash_value"
    }

    mock_cache = AsyncMock()
    mock_cache.get.return_value = json.dumps(cached_payload)
    mock_redis_client.redis = mock_cache

    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/private/resource",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 401
        assert "Please use valid token" in res.json()["description"]


@pytest.mark.asyncio
@patch("middlewares.jwt_validator.redis_async_client")
async def test_jwt_validator_valid_token_injects_state_and_succeeds(mock_redis_client):
    """Verify valid access token injects request.state claims and proceeds downstream."""
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    token = generate_test_jwt(user_id, session_id)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    cached_payload = {
        "id": session_id,
        "user_id": user_id,
        "is_active": True,
        "user_status": "ACTIVE",
        "access_token_hash": token_hash,
        "is_profile_completed": True
    }

    mock_cache = AsyncMock()
    mock_cache.get.return_value = json.dumps(cached_payload)
    mock_redis_client.redis = mock_cache

    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/private/resource",
            cookies={"access_token": token}  # Test cookie extraction fallback
        )
        assert res.status_code == 200
        data = res.json()
        assert data["user_id"] == user_id
        assert data["session_id"] == session_id
        assert data["user_status"] == "ACTIVE"
