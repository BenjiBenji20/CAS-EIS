import pytest
from pydantic import ValidationError
from modules.authentication.auth_schema import UserRegistrationRequest, UserRegistrationResponse
from utils.schema_response import SchemaResponseDetails


def test_user_registration_request_valid():
    """Test valid user registration request payload."""
    req = UserRegistrationRequest(
        username="valid_user_123",
        email="test@example.com",
        plain_password="Password123!"
    )
    assert req.username == "valid_user_123"
    assert req.email == "test@example.com"
    assert req.plain_password == "Password123!"


def test_user_registration_request_username_whitespace_strip():
    """Test that username leading/trailing whitespace is stripped."""
    req = UserRegistrationRequest(
        username="   john_doe   ",
        email="john@example.com",
        plain_password="SecurePassword1#"
    )
    assert req.username == "john_doe"


@pytest.mark.parametrize("invalid_username", [
    "usr",                    # Too short (< 5 chars)
    "user name",              # Contains space
    "user@domain",            # Contains illegal character @
    "user!",                  # Contains exclamation mark
])
def test_user_registration_request_invalid_username(invalid_username):
    """Test that invalid usernames trigger ValidationError."""
    with pytest.raises(ValidationError):
        UserRegistrationRequest(
            username=invalid_username,
            email="valid@example.com",
            plain_password="Password123!"
        )


@pytest.mark.parametrize("invalid_password", [
    "short1!",                # Too short (< 8 chars)
    "alllowercase1!",         # Missing uppercase
    "ALLUPPERCASE1!",         # Missing lowercase
    "NoSpecialChar123",       # Missing special character
    "NoDigitSymbol!!",        # Missing digit
])
def test_user_registration_request_invalid_password(invalid_password):
    """Test that weak or non-compliant passwords trigger ValidationError."""
    with pytest.raises(ValidationError):
        UserRegistrationRequest(
            username="validuser",
            email="valid@example.com",
            plain_password=invalid_password
        )


def test_user_registration_request_invalid_email():
    """Test that invalid email format raises ValidationError."""
    with pytest.raises(ValidationError):
        UserRegistrationRequest(
            username="validuser",
            email="not-an-email",
            plain_password="Password123!"
        )


def test_user_registration_response_serialization():
    """Test UserRegistrationResponse serialization and camelCase output."""
    res = UserRegistrationResponse(
        id="123e4567-e89b-12d3-a456-426614174000",
        username="john_doe",
        email="john@example.com",
        status="PENDING",
        response_details=SchemaResponseDetails(
            status=True,
            description="Success",
            count=1
        )
    )
    data = res.model_dump(by_alias=True)
    assert data["id"] == "123e4567-e89b-12d3-a456-426614174000"
    assert data["status"] == "PENDING"
    assert "responseDetails" in data
    assert data["responseDetails"]["status"] is True
