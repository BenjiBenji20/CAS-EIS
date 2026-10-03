import time
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from loguru import logger


class LoggingMiddleware(BaseHTTPMiddleware):
    """Global middleware that intercepts HTTP requests to trace execution flow,

    records execution duration, and outputs process logging metadata.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        start_time = time.perf_counter()

        # Inject request_id contextually into all logs generated within the request thread context
        with logger.contextualize(request_id=request_id):
            client_ip = request.client.host if request.client else "unknown"
            logger.info(
                f"Request started | Method: {request.method} | Path: {request.url.path} | Client IP: {client_ip}"
            )

            try:
                response = await call_next(request)
            except Exception as exc:
                elapsed = (time.perf_counter() - start_time) * 1000
                logger.error(
                    f"Request crashed | Method: {request.method} | Path: {request.url.path} | "
                    f"Duration: {elapsed:.2f}ms | Error: {str(exc)}"
                )
                raise exc

            elapsed = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"Request completed | Method: {request.method} | Path: {request.url.path} | "
                f"Status: {response.status_code} | Duration: {elapsed:.2f}ms"
            )

            response.headers["X-Request-ID"] = request_id
            return response
