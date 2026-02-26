"""Custom error handlers for consistent API error responses.

Produces the contract-compliant nested error format:
    { "error": { "code": "ERROR_CODE", "message": "Human-readable message" } }

Handles:
    - APIError: application-level errors raised by route/middleware code
    - RequestValidationError: Pydantic validation failures (422)
    - HTTPException: fallback for any raw FastAPI exceptions
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .models import APIError, ErrorDetail, ErrorResponse, FieldError

# Map HTTP status codes to default error codes
_STATUS_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
}


def register_error_handlers(app: FastAPI) -> None:
    """Register custom exception handlers on a FastAPI app.

    Call this once when setting up the application to ensure all errors
    follow the { error: { code, message, details? } } contract.
    """

    @app.exception_handler(APIError)
    async def api_error_handler(_request: Request, exc: APIError) -> JSONResponse:
        """Handle APIError with the full nested error format."""
        body = ErrorResponse(
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                details=exc.details,
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(exclude_none=True),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Convert Pydantic validation errors to the nested error format."""
        field_errors = []
        for err in exc.errors():
            loc = err.get("loc", ())
            # Skip the first element if it's 'body'
            field_path = ".".join(str(part) for part in loc if part != "body")
            field_errors.append(
                FieldError(field=field_path, message=err.get("msg", "Invalid value"))
            )

        body = ErrorResponse(
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="Request validation failed.",
                details=field_errors if field_errors else None,
            )
        )
        return JSONResponse(
            status_code=422,
            content=body.model_dump(exclude_none=True),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        _request: Request, exc: HTTPException
    ) -> JSONResponse:
        """Convert raw HTTPExceptions to the nested error format."""
        code = _STATUS_CODE_MAP.get(exc.status_code, "ERROR")
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

        body = ErrorResponse(
            error=ErrorDetail(code=code, message=message)
        )
        response = JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(exclude_none=True),
        )
        # Preserve headers (e.g., WWW-Authenticate, Retry-After)
        if exc.headers:
            for key, value in exc.headers.items():
                response.headers[key] = value
        return response
