from typing import Any, Optional


class AppException(Exception):
    """Base application exception for all custom domain and error handling."""

    def __init__(
        self,
        status_code: int = 500,
        message: str = "An unexpected error occurred",
        error_code: str = "INTERNAL_SERVER_ERROR",
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.error_code = error_code
        self.details = details


class NotFoundException(AppException):
    """Raised when a requested resource is not found (HTTP 404)."""

    def __init__(
        self,
        message: str = "Resource not found",
        error_code: str = "NOT_FOUND",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=404,
            message=message,
            error_code=error_code,
            details=details,
        )


class BadRequestException(AppException):
    """Raised for client-side errors, invalid payloads, or malformed data (HTTP 400)."""

    def __init__(
        self,
        message: str = "Bad request parameters",
        error_code: str = "BAD_REQUEST",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=400,
            message=message,
            error_code=error_code,
            details=details,
        )


class UnauthorizedException(AppException):
    """Raised when authentication credentials are missing or invalid (HTTP 401)."""

    def __init__(
        self,
        message: str = "Authentication failed",
        error_code: str = "UNAUTHORIZED",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=401,
            message=message,
            error_code=error_code,
            details=details,
        )


class ForbiddenException(AppException):
    """Raised when an authenticated client does not have required permissions (HTTP 403)."""

    def __init__(
        self,
        message: str = "Access forbidden",
        error_code: str = "FORBIDDEN",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=403,
            message=message,
            error_code=error_code,
            details=details,
        )


class ConflictException(AppException):
    """Raised when there is a state conflict, e.g., duplicate entries (HTTP 409)."""

    def __init__(
        self,
        message: str = "Resource conflict error",
        error_code: str = "CONFLICT",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=409,
            message=message,
            error_code=error_code,
            details=details,
        )


class InternalServerException(AppException):
    """Raised when an internal error occurs within the application domain (HTTP 500)."""

    def __init__(
        self,
        message: str = "Internal server error occurred",
        error_code: str = "INTERNAL_SERVER_ERROR",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=500,
            message=message,
            error_code=error_code,
            details=details,
        )


class TooManyRequestsException(AppException):
    """Raised when rate limit is exceeded (HTTP 429)."""

    def __init__(
        self,
        message: str = "Too many requests. Please try again later.",
        error_code: str = "RATE_LIMIT_EXCEEDED",
        details: Optional[Any] = None,
    ):
        super().__init__(
            status_code=429,
            message=message,
            error_code=error_code,
            details=details,
        )
