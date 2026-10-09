from uuid import UUID

from fastapi import Depends, Request
from loguru import logger
from pydantic import Field

from base.schema import BaseSchema
from exceptions.app_exception import UnauthorizedException
from modules.authentication.auth_service import AuthenticationService


class SudoCredentialRequest(BaseSchema):
    """Standard payload for critical administrative actions requiring step-up re-authentication."""
    admin_username: str = Field(..., description="Administrator username authorizing critical action")
    admin_password: str = Field(..., description="Active administrator password to authorize critical action")


async def verify_sudo_credential(
    user_id: UUID,
    username: str,
    plain_password: str,
    auth_service: AuthenticationService,
) -> None:
    """
    Programmatic helper verifying user credentials against DB password hash.
    Raises UnauthorizedException with code 'INVALID_ADMIN_CREDENTIALS' if validation fails.
    """
    is_valid = await auth_service.verify_admin_user_credential(
        user_id=user_id, username=username, plain_password=plain_password
    )
    if not is_valid:
        logger.warning(f"Sudo credential verification failed for user {user_id} ({username}).")
        raise UnauthorizedException(
            message="Invalid administrative credentials. Action aborted.",
            error_code="INVALID_ADMIN_CREDENTIALS",
        )
    logger.info(f"Sudo credential verification succeeded for user {user_id} ({username}).")


async def require_sudo_credential(
    credential: SudoCredentialRequest,
    request: Request,
    auth_service: AuthenticationService = Depends(),
) -> SudoCredentialRequest:
    """
    Validates caller's administrative credentials against the database before the route handler executes.
    """
    admin_user_id: UUID = getattr(request.state, "user_id", None)
    if not admin_user_id:
        logger.warning("require_sudo_credential invoked without authenticated user_id in request.state.")
        raise UnauthorizedException(message="Authentication required.")

    await verify_sudo_credential(
        user_id=admin_user_id,
        username=credential.admin_username,
        plain_password=credential.admin_password,
        auth_service=auth_service,
    )
    
    return credential
