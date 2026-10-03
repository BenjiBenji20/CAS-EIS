from core.settings import settings
from dependencies.rate_limit import rate_limit_by_ip
from fastapi import APIRouter, Depends, Request, Response, status

from modules.authentication.auth_schema import RefreshAuthenticationTokensResponse, UserRegistrationRequest, UserRegistrationResponse
from loguru import logger

from modules.authentication.auth_service import AuthenticationService
from modules.authentication.auth_schema import UserAuthenticationResponse, UserAuthenticationRequest


router = APIRouter(
    tags=[
        "Public: Register user, Authenticate User Grant JWT, JWTs and Revoke Old",
    ]
)

# User registration. Public access
@router.post(
    "/api/public/auth/registration",
    summary="User registration. Pending flag on success.",
    status_code=status.HTTP_201_CREATED,
    response_model=UserRegistrationResponse,
    dependencies=[Depends(rate_limit_by_ip())]
)
async def user_registration(
    user: UserRegistrationRequest,
    service: AuthenticationService = Depends()
):
    """Success registration status flag as PENDING for pooling."""
    logger.info("Accessing router for user registrations")
    return await service.register_user(user=user)


# User authentication. Public access
@router.post(
    "/api/public/auth/auth-tokens",
    summary="On success (HTTP 200 OK), grants access + refresh tokens.",
    status_code=status.HTTP_200_OK,
    response_model=UserAuthenticationResponse,
    dependencies=[Depends(rate_limit_by_ip())]
)
async def user_authentication(
    credential: UserAuthenticationRequest,
    request: Request,
    response: Response,
    service: AuthenticationService = Depends()
):
    logger.info("Accessing router for user authentication.")
    
    # Extract client IP (handling proxy X-Forwarded-For header)
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(",")[0].strip()
    else:
        ip_address = request.client.host if request.client else None
        
    user_agent = request.headers.get("User-Agent")

    auth_response = await service.authenticate_user(
        credential=credential,
        ip_address=ip_address,
        user_agent=user_agent
    )

    # Attach HTTP-Only Cookies on response
    if auth_response and auth_response.auth_token_payload:
        is_secure = settings.COOKIE_SECURE if settings.ENVIRONMENT != "dev" else False
        
        if auth_response.auth_token_payload.access_token:
            response.set_cookie(
                key="access_token",
                value=auth_response.auth_token_payload.access_token,
                httponly=True,
                secure=is_secure,
                samesite=settings.COOKIE_SAMESITE,
                max_age=settings.ACCESS_JWT_EXPIRY_SEC,
                path="/"
            )
        if auth_response.auth_token_payload.refresh_token:
            response.set_cookie(
                key="refresh_token",
                value=auth_response.auth_token_payload.refresh_token,
                httponly=True,
                secure=is_secure,
                samesite=settings.COOKIE_SAMESITE,
                max_age=settings.REFRESH_JWT_EXPIRY_SEC,
                path="/api/public/auth"
            )

    return auth_response
    
    
@router.post(
    "/api/public/auth/refresh-token",
    summary="Extract refresh token in cookies, verify signature using secret key and generate new access-token.",
    status_code=status.HTTP_200_OK,
    response_model=RefreshAuthenticationTokensResponse,
    dependencies=[Depends(rate_limit_by_ip())]
)
async def refresh_tokens(
    request: Request,
    response: Response,
    service: AuthenticationService = Depends()
):
    logger.info("Requesting for new access token.")
    refresh_token = request.cookies.get("refresh_token")
    new_access_token = await service.refresh_authentication_tokens(refresh_token=refresh_token)
    
    if new_access_token and new_access_token.auth_token_payload:
        is_secure = settings.COOKIE_SECURE if settings.ENVIRONMENT != "dev" else False
        if new_access_token.auth_token_payload.access_token:
            response.set_cookie(
                key="access_token",
                value=new_access_token.auth_token_payload.access_token,
                httponly=True,
                secure=is_secure,
                samesite=settings.COOKIE_SAMESITE,
                max_age=settings.ACCESS_JWT_EXPIRY_SEC,
                path="/"
            )
        if new_access_token.auth_token_payload.refresh_token:
            response.set_cookie(
                key="refresh_token",
                value=new_access_token.auth_token_payload.refresh_token,
                httponly=True,
                secure=is_secure,
                samesite=settings.COOKIE_SAMESITE,
                max_age=settings.REFRESH_JWT_EXPIRY_SEC,
                path="/api/public/auth"
            )
            
    return new_access_token

