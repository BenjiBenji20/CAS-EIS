import hashlib
import json
from uuid import UUID
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import jwt
from loguru import logger

from clients.redis import redis_async_client
from core.settings import settings
from exceptions.exception_handlers import ErrorDetailsSchema, ErrorResponseSchema
from utils.maintain_cache_key import MaintainCacheKeyUtils


class JWTValidator(BaseHTTPMiddleware):
    """
    High-performance, Zero-DB JWT Validation Middleware for private ERP routes.
    Executes in-memory CPU verification + Redis O(1) session checks (~0.5ms).
    Injects pre-verified claims into request.state for 0ms downstream route access.
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.cache_utils = MaintainCacheKeyUtils()
        self.public_excluded_paths = {
            settings.API_DOCS_URL,
            settings.API_REDOC_URL,
            settings.OPENAPI_URL,
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
        }

    def _create_error_response(self, status_code: int, message: str, error_code: str) -> JSONResponse:
        response_model = ErrorResponseSchema(
            description=message,
            error=ErrorDetailsSchema(code=error_code)
        )
        content = response_model.model_dump(mode="json", by_alias=True)
        return JSONResponse(status_code=status_code, content=content)

    async def dispatch(self, request: Request, call_next):
        req_path = request.url.path

        # ----------------------------------------------------------------------
        # DYNAMIC ROUTE EXCLUSION GUARD
        # ----------------------------------------------------------------------
        if req_path.startswith("/api/public") or req_path in self.public_excluded_paths:
            return await call_next(request)

        # ----------------------------------------------------------------------
        # TOKEN EXTRACTION GUARD
        # ----------------------------------------------------------------------
        auth_header = request.headers.get("Authorization")
        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        else:
            token = request.cookies.get("access_token")

        if not token:
            logger.warning(f"Access token missing for private route request: {req_path}")
            return self._create_error_response(
                status_code=401,
                message="Invalid request. Authentication required.",
                error_code="UNAUTHORIZED"
            )

        # ----------------------------------------------------------------------
        # CRYPTOGRAPHIC SIGNATURE & EXPIRY GUARD (PURE CPU - 0ms I/O)
        # ----------------------------------------------------------------------
        try:
            payload: dict = jwt.decode(
                token,
                key=str(settings.ACCESS_JWT_SECRET_KEY),
                algorithms=[settings.JWT_ALGORITHM]
            )
        except jwt.ExpiredSignatureError:
            logger.warning("Access token is expired.")
            return self._create_error_response(
                status_code=401,
                message="Invalid request. Session expired",
                error_code="UNAUTHORIZED"
            )
        except jwt.PyJWTError as e:
            logger.warning(f"JWT signature verification failed: {e}")
            return self._create_error_response(
                status_code=401,
                message="Invalid authentication key.",
                error_code="UNAUTHORIZED"
            )

        if payload.get("type") != "access-token":
            logger.warning(f"Invalid token type provided: {payload.get('type')}")
            return self._create_error_response(
                status_code=401,
                message="Invalid request. Unauthorized access.",
                error_code="UNAUTHORIZED"
            )

        user_id = payload.get("sub")
        session_id = payload.get("sid")

        if not user_id or not session_id:
            logger.warning("Invalid token claims: sub or sid missing.")
            return self._create_error_response(
                status_code=401,
                message="Invalid access. Failed authentication or missing key.",
                error_code="UNAUTHORIZED"
            )

        # ----------------------------------------------------------------------
        # REDIS SESSION & USER STATUS VALIDATION GUARD (O(1) ~0.5ms)
        # ----------------------------------------------------------------------
        try:
            async_cache = redis_async_client.redis
            cache_key = self.cache_utils.create_cache_key(
                session_id=str(session_id),
                user_id=str(user_id)
            )
            cached_session_raw = await async_cache.get(cache_key)

            if cached_session_raw is None:
                logger.warning(f"Session key {cache_key} not found in Redis (revoked/expired).")
                return self._create_error_response(
                    status_code=401,
                    message="Session has expired or been revoked.",
                    error_code="UNAUTHORIZED"
                )

            session_payload: dict = json.loads(cached_session_raw) if isinstance(cached_session_raw, (str, bytes)) else cached_session_raw

            # Validation #1: Active Session Flag
            if not session_payload.get("is_active"):
                logger.warning(f"Session {session_id} is marked inactive in Redis.")
                return self._create_error_response(
                    status_code=401,
                    message="Session is inactive. Please log in again.",
                    error_code="UNAUTHORIZED"
                )

            # Validation #2: User Account Status Flag (Instant Ban / Suspension Check)
            user_status = session_payload.get("user_status", "ACTIVE")
            if str(user_status).upper() != "ACTIVE":
                logger.warning(f"User {user_id} account status is {user_status}. Access blocked.")
                return self._create_error_response(
                    status_code=403,
                    message=f"Account is {user_status.lower()}. Access forbidden.",
                    error_code="FORBIDDEN"
                )

            # Validation #3: Single Active Access Token Check (Instant Invalidation on RTR)
            cached_at_hash = session_payload.get("access_token_hash")
            if cached_at_hash:
                incoming_at_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
                if incoming_at_hash != cached_at_hash:
                    logger.warning(f"Stale/rotated access token presented for session {session_id}.")
                    return self._create_error_response(
                        status_code=401,
                        message="Invalid requests. Please use valid token.",
                        error_code="UNAUTHORIZED"
                    )

            # ------------------------------------------------------------------
            # CONTEXT INJECTION (request.state)
            # ------------------------------------------------------------------
            request.state.user_id = UUID(str(user_id))
            request.state.session_id = UUID(str(session_id))
            request.state.user_status = str(user_status)
            request.state.is_profile_completed = bool(session_payload.get("is_profile_completed", True))

        except Exception as e:
            logger.exception(f"Unexpected error during Redis session validation in middleware: {e}")
            return self._create_error_response(
                status_code=500,
                message="Unexpected error validating session.",
                error_code="INTERNAL_SERVER_ERROR"
            )

        return await call_next(request)
