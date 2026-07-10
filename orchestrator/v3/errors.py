"""Typed error envelope and stable code registry (REQ-BE-053, contract §1.6).

Every non-2xx REST response and every WS ``error`` payload uses the shape::

    {"error": {"code", "message", "retriable", "details"}}

The :data:`ERROR_REGISTRY` maps each stable ``code`` to its HTTP status and
``retriable`` flag exactly as frozen in ``API_CONTRACT_V3.md``. Raise
:class:`ApiError` anywhere in the V3 stack; :func:`install_error_handlers` turns
it (and FastAPI validation errors) into the contract envelope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# code -> (http_status, retriable)
ERROR_REGISTRY: dict[str, tuple[int, bool]] = {
    "unauthorized": (401, False),
    "forbidden": (403, False),
    "incompatible_version": (409, False),
    "not_found": (404, False),
    "validation_error": (422, False),
    "revision_conflict": (409, False),
    "cap_exceeded": (409, False),
    "ceiling_reached": (409, False),
    "illegal_transition": (409, False),
    "memory_write_denied": (403, False),
    "conductor_write_forbidden": (403, False),
    "memory_too_large": (413, False),
    "memory_quota_exceeded": (409, False),
    "path_escape": (400, False),
    "plan_expired": (410, False),
    "plan_already_confirmed": (409, False),
    "session_not_found": (404, False),
    "rate_limited": (429, True),
    "orchestrator_error": (500, True),
    "provider_error": (502, True),
}


@dataclass
class ApiError(Exception):
    """A typed, contract-registered error.

    Args:
        code: A key from :data:`ERROR_REGISTRY`.
        message: Human-readable explanation (safe for the UI; no secrets).
        details: Optional structured context (e.g. ``{"card_id", "expected_revision"}``).
        status: Override HTTP status; defaults to the registry mapping.
        retriable: Override retriable flag; defaults to the registry mapping.
    """

    code: str
    message: str = ""
    details: dict[str, Any] | None = None
    status: int | None = None
    retriable: bool | None = None

    def __post_init__(self) -> None:
        reg_status, reg_retriable = ERROR_REGISTRY.get(self.code, (500, False))
        if self.status is None:
            self.status = reg_status
        if self.retriable is None:
            self.retriable = reg_retriable
        if not self.message:
            self.message = self.code.replace("_", " ")
        super().__init__(self.message)

    def envelope(self) -> dict[str, Any]:
        """Return the ``{"error": {...}}`` body for REST and WS ``error`` frames."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retriable": bool(self.retriable),
                "details": self.details or {},
            }
        }


def error_body(code: str, message: str = "", details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a bare error envelope dict without raising."""
    return ApiError(code=code, message=message, details=details).envelope()


def install_error_handlers(app: FastAPI) -> None:
    """Register exception handlers that emit the contract error envelope."""

    @app.exception_handler(ApiError)
    async def _api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:  # noqa: ANN401
        return JSONResponse(status_code=exc.status or 500, content=exc.envelope())

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        err = ApiError(
            code="validation_error",
            message="Malformed request body or parameters.",
            details={"errors": _safe_errors(exc)},
        )
        return JSONResponse(status_code=err.status or 422, content=err.envelope())


def _safe_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Render pydantic validation errors as JSON-safe dicts (no bytes/exceptions)."""
    out: list[dict[str, Any]] = []
    for e in exc.errors():
        out.append(
            {
                "loc": [str(p) for p in e.get("loc", [])],
                "msg": str(e.get("msg", "")),
                "type": str(e.get("type", "")),
            }
        )
    return out


__all__ = [
    "ERROR_REGISTRY",
    "ApiError",
    "error_body",
    "install_error_handlers",
]
