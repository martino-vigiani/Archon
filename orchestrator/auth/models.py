"""Data models for authentication - User, Role, request/response schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class Role(str, Enum):
    """User roles for access control."""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"

    @classmethod
    def has_permission(cls, user_role: Role, required_role: Role) -> bool:
        """Check if user_role has at least the permissions of required_role.

        Hierarchy: ADMIN > OPERATOR > VIEWER
        """
        hierarchy = {cls.VIEWER: 0, cls.OPERATOR: 1, cls.ADMIN: 2}
        return hierarchy.get(user_role, -1) >= hierarchy.get(required_role, 999)


@dataclass
class User:
    """Internal user representation with hashed password."""

    id: str = field(default_factory=lambda: uuid4().hex)
    username: str = ""
    email: str = ""
    hashed_password: str = ""
    role: Role = Role.VIEWER
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary (excludes password)."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> User:
        """Create User from database row tuple."""
        return cls(
            id=row[0],
            username=row[1],
            email=row[2],
            hashed_password=row[3],
            role=Role(row[4]),
            is_active=bool(row[5]),
            created_at=row[6],
            updated_at=row[7],
        )


# --- Pydantic schemas for API request/response ---


class UserCreate(BaseModel):
    """Request schema for user registration."""

    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    role: Role = Role.VIEWER

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        if not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError("Username must be alphanumeric (dashes and underscores allowed)")
        return v.lower()

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v.lower()


class UserResponse(BaseModel):
    """Response schema for user data (no password)."""

    id: str
    username: str
    email: str
    role: Role
    is_active: bool
    created_at: str
    updated_at: str


class LoginRequest(BaseModel):
    """Request schema for login."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Response schema for token endpoints."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    """Request schema for token refresh."""

    refresh_token: str


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


# --- Error response schemas (contract: nested {error: {code, message}} format) ---


class FieldError(BaseModel):
    """Per-field validation error detail."""

    field: str
    message: str


class ErrorDetail(BaseModel):
    """Nested error object within ErrorResponse."""

    code: str
    message: str
    details: list[FieldError] | None = None


class ErrorResponse(BaseModel):
    """Standard API error response: { error: { code, message, details? } }.

    Agreed format per RESTAPIContract between T1 and T2.
    All API errors MUST use this shape.
    """

    error: ErrorDetail


class APIError(Exception):
    """Application-level error that renders as { error: { code, message } }.

    Use instead of FastAPI's HTTPException to produce the contract-compliant
    nested error format.

    Example:
        raise APIError(
            status_code=401,
            code="INVALID_CREDENTIALS",
            message="Email or password is incorrect.",
        )
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[FieldError] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)
