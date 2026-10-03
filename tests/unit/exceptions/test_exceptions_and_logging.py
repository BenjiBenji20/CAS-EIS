import pytest
import uuid
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from pydantic import BaseModel, Field

from exceptions.app_exception import NotFoundException, BadRequestException
from exceptions.exception_handlers import register_exception_handlers
from core.logging_middleware import LoggingMiddleware

# Create isolated FastAPI instance for testing setup
dummy_app = FastAPI()
dummy_app.add_middleware(LoggingMiddleware)
register_exception_handlers(dummy_app)


class DummyValidationSchema(BaseModel):
    user_name: str = Field(..., min_length=5)
    plain_password: str = Field(..., min_length=8)


@dummy_app.get("/test-not-found")
async def route_not_found():
    raise NotFoundException(
        message="Specific resource was not located",
        error_code="RESOURCE_ABSENT",
        details={"resourceId": 123}
    )


@dummy_app.post("/test-validation")
async def route_validation(payload: DummyValidationSchema):
    return {"status": "ok"}


@dummy_app.get("/test-unhandled")
async def route_unhandled():
    raise ValueError("Database connection dropped unexpectedly")


@pytest.fixture
async def test_client():
    """Async Client dedicated to our dummy_app instance."""
    transport = ASGITransport(app=dummy_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_custom_app_exception_handling(test_client: AsyncClient):
    """Verify AppException is intercepted and returns correct format & status."""
    response = await test_client.get("/test-not-found")
    assert response.status_code == 404

    data = response.json()
    assert data["status"] is False
    assert data["description"] == "Specific resource was not located"
    assert "dateTime" in data  # camelCase validation
    assert data["error"]["code"] == "RESOURCE_ABSENT"
    assert data["error"]["details"] == {"resourceId": 123}


@pytest.mark.asyncio
async def test_validation_error_camelcase_formatting(test_client: AsyncClient):
    """Verify standard validation errors map error fields to camelCase."""
    # Send incorrect payloads to trigger Pydantic validation
    bad_payload = {
        "user_name": "usr",          # Less than 5 chars
        "plain_password": "short"    # Less than 8 chars
    }
    response = await test_client.post("/test-validation", json=bad_payload)
    assert response.status_code == 422

    data = response.json()
    assert data["status"] is False
    assert data["description"] == "Request validation failed"
    assert data["error"]["code"] == "VALIDATION_ERROR"
    
    details = data["error"]["details"]
    assert len(details) == 2
    
    # Confirm field names in validation details were converted to camelCase
    fields = [err["field"] for err in details]
    assert "userName" in fields
    assert "plainPassword" in fields


@pytest.mark.asyncio
async def test_unhandled_system_exception_masking(test_client: AsyncClient):
    """Verify that generic exceptions are masked with standard 500 payload."""
    response = await test_client.get("/test-unhandled")
    assert response.status_code == 500

    data = response.json()
    assert data["status"] is False
    assert data["description"] == "An unexpected internal server error occurred"
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert data["error"]["details"] is None  # Ensures internal traceback is hidden


@pytest.mark.asyncio
async def test_logging_middleware_request_id_injection(test_client: AsyncClient):
    """Verify correlation ID (X-Request-ID) is generated and returned."""
    response = await test_client.get("/test-not-found")
    assert "X-Request-ID" in response.headers
    
    # Check that it compiles to a valid UUID
    request_id = response.headers["X-Request-ID"]
    assert uuid.UUID(request_id)
