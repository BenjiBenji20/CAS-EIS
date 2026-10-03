import re
from modules.profile.user_profile_schema import UserProfileResponse
from pydantic import BaseModel, EmailStr, Field, field_validator

from base.schema import BaseSchema
from utils.schema_response import SchemaResponseDetails

class UserAuthenticationRequest(BaseSchema):
    username: str = Field(
        description="Username for authentication credential.",
        min_length=5,
        max_length=50,
    )
    plain_password: str = Field(
        description="User plain text password.",
        min_length=8,
        max_length=50,
    )
    
    
class AuthenticationTokenPayload(BaseSchema):
    access_token: str | None = None
    refresh_token: str | None = None
    
    
class RefreshAuthenticationTokensResponse(BaseSchema):
    # auth tokens on success
    auth_token_payload: AuthenticationTokenPayload | None = None 
    response_details: SchemaResponseDetails


class UserAuthenticationResponse(BaseSchema):
    session_id: str | None = None
    user_id: str | None = None
    username: str | None = None
    email: str | None = None
    status: str | None = None
    is_profile_completed: bool = False
    # auth tokens on success
    auth_token_payload: AuthenticationTokenPayload | None = None 
    # to add personal information responses
    user_profile_payload: UserProfileResponse | None = None
    response_details: SchemaResponseDetails | None = None
    

# Regex Patterns
USERNAME_REGEX = r"^[a-zA-Z0-9_-]+$"
PASSWORD_REGEX = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#])[A-Za-z\d@$!%*?&#]{8,50}$"


class UserRegistrationRequest(UserAuthenticationRequest):
    email: EmailStr = Field(
        description="User email address.",
        max_length=100,
    )

    @field_validator('username')
    @classmethod
    def validate_username(cls, val: str) -> str:
        val = val.strip()
        if not re.match(USERNAME_REGEX, val):
            raise ValueError(
                'Username can only contain alphanumeric characters, underscores, and hyphens.'
            )
        return val

    @field_validator('plain_password')
    @classmethod
    def validate_password(cls, val: str) -> str:
        if not re.match(PASSWORD_REGEX, val):
            raise ValueError(
                'Password must be 8-50 characters long and contain at least one uppercase letter, '
                'one lowercase letter, one number, and one special character (@$!%*?&#).'
            )
        return val


class UserRegistrationResponse(BaseSchema):
    id: str | None = None
    username: str | None = None
    email: str | None = None
    status: str | None = "PENDING"
    response_details: SchemaResponseDetails
