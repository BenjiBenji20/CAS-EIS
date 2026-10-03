from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import Field
from pydantic.alias_generators import to_camel

from base.schema import BaseSchema
from exceptions.app_exception import AppException


class ErrorDetailsSchema(BaseSchema):
    code: str = Field(description="System-defined machine-readable error code")
    details: Optional[Any] = Field(None, description="Detailed context of the error")


class ErrorResponseSchema(BaseSchema):
    status: bool = Field(False, description="Indicates call success state (always false for errors)")
    description: str = Field(description="Human-readable summary of the error")
    date_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the error response was generated"
    )
    error: ErrorDetailsSchema = Field(description="Structured details about the exception")


def format_validation_errors(exc: RequestValidationError) -> List[dict]:
    """Formats validation errors by converting field names into camelCase.

    This ensures consistency with front-end naming conventions.
    """
    formatted = []
    for error in exc.errors():
        # Retrieve location of the error path, e.g. ("body", "plain_password")
        path = list(error.get("loc", []))
        cleaned_path = []
        for i, item in enumerate(path):
            if isinstance(item, str):
                # Omit prefix markers like 'body', 'query', etc.
                if i == 0 and item in ("body", "query", "path", "header"):
                    continue
                cleaned_path.append(to_camel(item))
            else:
                cleaned_path.append(item)

        field_name = ".".join(map(str, cleaned_path)) if cleaned_path else "payload"
        formatted.append({
            "field": field_name,
            "message": error.get("msg"),
            "type": error.get("type"),
        })
    return formatted


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handles domain-specific custom exceptions (AppException)."""
    # Choose log level depending on the severity of the exception status code
    if exc.status_code >= 500:
        logger.error(f"Application error [{exc.error_code}]: {exc.message}")
    else:
        logger.warning(f"Client warning [{exc.error_code}]: {exc.message}")

    response_model = ErrorResponseSchema(
        description=exc.message,
        error=ErrorDetailsSchema(code=exc.error_code, details=exc.details)
    )
    # Serialize to dict, respecting Pydantic configuration (camelCase conversion & JSON types)
    content = response_model.model_dump(mode="json", by_alias=True)
    return JSONResponse(status_code=exc.status_code, content=content)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handles standard FastAPI RequestValidationError."""
    errors = format_validation_errors(exc)
    logger.warning(f"Request validation failed for path {request.url.path}: {errors}")

    response_model = ErrorResponseSchema(
        description="Request validation failed",
        error=ErrorDetailsSchema(code="VALIDATION_ERROR", details=errors)
    )
    content = response_model.model_dump(mode="json", by_alias=True)
    return JSONResponse(status_code=422, content=content)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handles all uncaught standard Python exceptions to prevent internal leakages."""
    logger.exception(f"Unhandled system error occurred while processing {request.method} {request.url.path}")

    response_model = ErrorResponseSchema(
        description="An unexpected internal server error occurred",
        error=ErrorDetailsSchema(code="INTERNAL_SERVER_ERROR")
    )
    content = response_model.model_dump(mode="json", by_alias=True)
    return JSONResponse(status_code=500, content=content)


def register_exception_handlers(app: FastAPI) -> None:
    """Helper function to bind exception handlers to the FastAPI app instance."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
