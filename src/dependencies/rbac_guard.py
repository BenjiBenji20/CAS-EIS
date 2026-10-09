from enum import Enum
from typing import Callable, Union
from uuid import UUID

from exceptions.app_exception import ForbiddenException, UnauthorizedException
from fastapi import Depends, Request
from loguru import logger

from modules.rbac.rbac_service import RBACService


def _extract_str(val: Union[str, Enum]) -> str:
    return val.value if isinstance(val, Enum) else str(val)


def require_permission(permission_code: Union[str, Enum]) -> Callable:
    """
    Declarative FastAPI Dependency Guard enforcing a specific permission code.
    Accepts both string codes or SystemPermission Enum.
    
    Usage:
    @router.post("/users", dependencies=[Depends(require_permission(SystemPermission.AUTHENTICATION_USER_CREATE))])
    """
    code_str = _extract_str(permission_code)

    async def permission_dependency(
        request: Request,
        rbac_service: RBACService = Depends()
    ) -> UUID:
        user_id: UUID = getattr(request.state, "user_id", None)
        if not user_id:
            logger.warning("require_permission invoked without authenticated user_id in request.state.")
            raise UnauthorizedException(message="Authentication required.")

        user_perms = await rbac_service.get_or_cache_user_permissions(user_id)

        # Superadmin role global bypass
        if "SUPER_ADMIN" in user_perms.roles:
            return user_id

        # Permission code check
        if code_str not in user_perms.permissions:
            logger.warning(f"Access denied for user {user_id}: missing permission '{code_str}'.")
            raise ForbiddenException(
                message="Permission denied.",
                error_code="PERMISSION_DENIED"
            )

        return user_id

    return permission_dependency


def require_any_permission(*permission_codes: Union[str, Enum]) -> Callable:
    """
    Declarative FastAPI Dependency Guard enforcing at least one of the listed permission codes.
    
    Usage:
    @router.get("/orders", dependencies=[Depends(require_any_permission(SystemPermission.AUTHENTICATION_USER_READ, SystemPermission.AUTHENTICATION_USER_UPDATE))])
    """
    code_strs = [_extract_str(c) for c in permission_codes]

    async def any_permission_dependency(
        request: Request,
        rbac_service: RBACService = Depends()
    ) -> UUID:
        user_id: UUID = getattr(request.state, "user_id", None)
        if not user_id:
            raise UnauthorizedException(message="Authentication required.")

        user_perms = await rbac_service.get_or_cache_user_permissions(user_id)

        if "SUPER_ADMIN" in user_perms.roles:
            return user_id

        has_match = any(code in user_perms.permissions for code in code_strs)
        if not has_match:
            logger.warning(f"Access denied for user {user_id}: missing any of permissions {code_strs}.")
            raise ForbiddenException(
                message="Permission denied. Insufficient privileges.",
                error_code="PERMISSION_DENIED"
            )

        return user_id

    return any_permission_dependency


def require_role(*role_names: Union[str, Enum]) -> Callable:
    """
    Declarative FastAPI Dependency Guard enforcing at least one of the listed role names.
    
    Usage:
    @router.get("/admin/dashboard", dependencies=[Depends(require_role(RoleName.SUPER_ADMIN, RoleName.ADMIN))])
    """
    role_strs = [_extract_str(r) for r in role_names]

    async def role_dependency(
        request: Request,
        rbac_service: RBACService = Depends()
    ) -> UUID:
        user_id: UUID = getattr(request.state, "user_id", None)
        if not user_id:
            raise UnauthorizedException(message="Authentication required.")

        user_perms = await rbac_service.get_or_cache_user_permissions(user_id)

        if "SUPER_ADMIN" in user_perms.roles:
            return user_id

        has_role_match = any(role in user_perms.roles for role in role_strs)
        if not has_role_match:
            logger.warning(f"Access denied for user {user_id}: missing required role from {role_strs}.")
            raise ForbiddenException(
                message="Access denied. Required role not assigned.",
                error_code="ROLE_NOT_ASSIGNED"
            )

        return user_id

    return role_dependency
