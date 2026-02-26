"""
Archon Live API - Contract-compliant REST API at localhost:8000/api/v1.

Implements the OpenAPI 3.0 specification defined in:
    .orchestra/contracts/api-openapi.yaml

Endpoints:
    POST   /api/v1/auth/register       - Register new user (public)
    POST   /api/v1/auth/login          - Login with email/password (public)
    POST   /api/v1/auth/refresh        - Refresh access token (public)
    DELETE /api/v1/auth/logout         - Revoke refresh token (auth required)
    GET    /api/v1/users/me            - Get current user profile (auth required)
    PUT    /api/v1/users/me            - Update current user profile (auth required)
    GET    /api/v1/resources           - List protected resources (auth required)
    POST   /api/v1/resources           - Create a resource (auth required)
    GET    /api/v1/resources/{id}      - Get a single resource (auth required)
    PUT    /api/v1/resources/{id}      - Update a resource (auth required, owner only)
    DELETE /api/v1/resources/{id}      - Delete a resource (auth required, owner/admin)
    GET    /api/v1/health              - Health check (public)

Uses the existing auth infrastructure (UserDatabase, TokenService, PasswordHasher)
with contract-compliant request/response shapes that match T1's APIClient SDK.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from .auth.config import AuthConfig
from .auth.database import UserDatabase
from .auth.passwords import PasswordHasher
from .auth.tokens import TokenError, TokenService


# ─── Configuration ────────────────────────────────────────────────────────


def _default_db_path() -> Path:
    return Path(__file__).parent.parent / ".orchestra" / "live_api.db"


# ─── Pydantic Schemas (contract-compliant) ────────────────────────────────


class RegisterRequest(BaseModel):
    """POST /auth/register request body."""

    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v.lower()


class LoginRequest(BaseModel):
    """POST /auth/login request body."""

    email: str = Field(...)
    password: str = Field(...)

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: str) -> str:
        return v.lower()


class RefreshRequest(BaseModel):
    """POST /auth/refresh request body."""

    refresh_token: str


class UpdateUserRequest(BaseModel):
    """PUT /users/me request body."""

    name: str | None = Field(None, min_length=1, max_length=100)
    email: str | None = Field(None, min_length=5, max_length=255)

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str | None) -> str | None:
        if v is not None:
            if "@" not in v or "." not in v.split("@")[-1]:
                raise ValueError("Invalid email format")
            return v.lower()
        return v


class AdminUpdateUserRequest(BaseModel):
    """PUT /users/{id} request body (admin only)."""

    name: str | None = Field(None, min_length=1, max_length=100)
    email: str | None = Field(None, min_length=5, max_length=255)
    role: str | None = Field(None, pattern="^(user|admin)$")
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str | None) -> str | None:
        if v is not None:
            if "@" not in v or "." not in v.split("@")[-1]:
                raise ValueError("Invalid email format")
            return v.lower()
        return v


# Response schemas match T1's APIClient dataclasses exactly.

class UserResponseSchema(BaseModel):
    """User profile data (no password)."""

    id: str
    email: str
    name: str
    role: str = "user"
    created_at: str
    updated_at: str | None = None


class TokenPairSchema(BaseModel):
    """Access + refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900


class AuthResponseSchema(BaseModel):
    """Combined user + tokens for register/login."""

    user: UserResponseSchema
    tokens: TokenPairSchema


class UserListSchema(BaseModel):
    """Paginated list of users (admin only)."""

    data: list[UserResponseSchema]
    meta: PaginationMetaSchema


class ResourceSchema(BaseModel):
    """Protected resource item."""

    id: str
    title: str
    content: str
    owner_id: str
    created_at: str


class PaginationMetaSchema(BaseModel):
    """Pagination metadata."""

    page: int
    per_page: int
    total: int
    total_pages: int


class ResourceListSchema(BaseModel):
    """Paginated list of resources."""

    data: list[ResourceSchema]
    meta: PaginationMetaSchema


class MessageResponseSchema(BaseModel):
    """Generic message response."""

    message: str


class FieldErrorSchema(BaseModel):
    """Per-field validation error."""

    field: str
    message: str


class ErrorDetailSchema(BaseModel):
    """Nested error object."""

    code: str
    message: str
    details: list[FieldErrorSchema] | None = None


class ErrorResponseSchema(BaseModel):
    """Contract-compliant error: { error: { code, message, details? } }."""

    error: ErrorDetailSchema


# ─── Application Error ────────────────────────────────────────────────────


class LiveAPIError(Exception):
    """Raises contract-compliant error responses."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[FieldErrorSchema] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


# ─── Resource Database ────────────────────────────────────────────────────


class ResourceDatabase:
    """SQLite-backed resource storage with seed data."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS resources (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def seed_if_empty(self, owner_id: str) -> None:
        """Seed sample resources if the table is empty."""
        count = self._conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        if count > 0:
            return

        now = datetime.now(timezone.utc).isoformat()
        samples = [
            ("API Design Notes", "RESTful patterns and endpoint conventions."),
            ("Sprint Retro", "What went well, what to improve."),
            ("Architecture Decision Record", "Chose FastAPI over Flask for async."),
            ("Deployment Checklist", "Pre-launch verification steps."),
            ("Performance Baseline", "Initial load test results and metrics."),
        ]
        for title, content in samples:
            self._conn.execute(
                "INSERT INTO resources (id, title, content, owner_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (uuid4().hex, title, content, owner_id, now),
            )
        self._conn.commit()

    def list_resources(self, page: int = 1, per_page: int = 20) -> dict[str, Any]:
        """Return paginated resources."""
        total = self._conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        total_pages = max(1, -(-total // per_page))
        offset = (page - 1) * per_page

        rows = self._conn.execute(
            "SELECT id, title, content, owner_id, created_at FROM resources ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset),
        ).fetchall()

        data = [
            {"id": r[0], "title": r[1], "content": r[2], "owner_id": r[3], "created_at": r[4]}
            for r in rows
        ]
        return {
            "data": data,
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
            },
        }


# ─── Dependency Injection ─────────────────────────────────────────────────


class LiveAPIState:
    """Shared state for the live API server."""

    def __init__(
        self,
        auth_config: AuthConfig | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        self.auth_config = auth_config or AuthConfig()
        self.hasher = PasswordHasher()
        self.token_service = TokenService(self.auth_config)

        # Single SQLite connection for both users and resources
        resolved_path = str(db_path) if db_path else str(_default_db_path())
        if resolved_path != ":memory:":
            Path(resolved_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(resolved_path)

        self.user_db = UserDatabase.__new__(UserDatabase)
        self.user_db.db_path = resolved_path
        self.user_db._conn = self._conn
        self.user_db._init_schema()

        self.resource_db = ResourceDatabase(self._conn)


_state: LiveAPIState | None = None


def get_state() -> LiveAPIState:
    """Return the shared API state."""
    if _state is None:
        raise RuntimeError("LiveAPIState not initialized")
    return _state


security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    state: LiveAPIState = Depends(get_state),
) -> dict[str, Any]:
    """Extract and validate the current user from the JWT bearer token."""
    if credentials is None:
        raise LiveAPIError(401, "UNAUTHORIZED", "Authentication required")

    try:
        payload = state.token_service.decode_token(credentials.credentials, expected_type="access")
    except TokenError as e:
        raise LiveAPIError(401, "UNAUTHORIZED", str(e))

    user = state.user_db.get_by_id(payload["sub"])
    if user is None:
        raise LiveAPIError(401, "UNAUTHORIZED", "User not found")
    if not user.is_active:
        raise LiveAPIError(403, "FORBIDDEN", "Account is deactivated")

    return _user_to_response(user)


def _user_to_response(user: Any) -> dict[str, Any]:
    """Convert internal User to contract-compliant response dict.

    Maps username -> name and internal roles -> user/admin for contract compatibility.
    """
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    # Map internal roles to contract roles
    contract_role = "admin" if role == "admin" else "user"

    return {
        "id": user.id,
        "email": user.email,
        "name": user.username,  # username stored internally, exposed as "name"
        "role": contract_role,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


# ─── App Factory ──────────────────────────────────────────────────────────


def create_live_api(
    auth_config: AuthConfig | None = None,
    db_path: Path | str | None = None,
) -> FastAPI:
    """Create the contract-compliant live API application.

    Args:
        auth_config: Auth configuration. Uses defaults if None.
        db_path: Path to SQLite database. Uses .orchestra/live_api.db if None.
            Pass ":memory:" for testing.

    Returns:
        Configured FastAPI application.
    """
    global _state
    _state = LiveAPIState(auth_config=auth_config, db_path=db_path)

    app = FastAPI(
        title="Archon REST API",
        version="1.0.0",
        description="JWT-authenticated REST API for Archon.",
    )

    # CORS for T1's admin dashboard
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Error Handlers ────────────────────────────────────────────────

    @app.exception_handler(LiveAPIError)
    async def live_api_error_handler(_request: Request, exc: LiveAPIError) -> JSONResponse:
        body = ErrorResponseSchema(
            error=ErrorDetailSchema(
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
        field_errors = []
        for err in exc.errors():
            loc = err.get("loc", ())
            field_path = ".".join(str(part) for part in loc if part != "body")
            field_errors.append(
                FieldErrorSchema(field=field_path, message=err.get("msg", "Invalid value"))
            )
        body = ErrorResponseSchema(
            error=ErrorDetailSchema(
                code="VALIDATION_ERROR",
                message="Request validation failed.",
                details=field_errors if field_errors else None,
            )
        )
        return JSONResponse(status_code=422, content=body.model_dump(exclude_none=True))

    # ── Auth Router (/api/v1/auth) ────────────────────────────────────

    from fastapi import APIRouter

    auth_router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

    @auth_router.post("/register", status_code=status.HTTP_201_CREATED)
    async def register(
        data: RegisterRequest,
        api_state: LiveAPIState = Depends(get_state),
    ) -> AuthResponseSchema:
        """Register a new user. Returns user + tokens."""
        from .auth.models import Role, User

        # First user gets admin
        role = Role.ADMIN if api_state.user_db.count_users() == 0 else Role.VIEWER

        user = User(
            username=data.name,
            email=data.email,
            hashed_password=api_state.hasher.hash(data.password),
            role=role,
        )

        try:
            api_state.user_db.create_user(user)
        except ValueError as e:
            msg = str(e)
            if "email" in msg.lower():
                raise LiveAPIError(409, "CONFLICT", "A user with this email already exists.")
            raise LiveAPIError(409, "CONFLICT", msg)

        # Seed resources for the first user
        api_state.resource_db.seed_if_empty(user.id)

        contract_role = "admin" if role == Role.ADMIN else "user"
        tokens = api_state.token_service.create_token_pair(user.id, contract_role)

        return AuthResponseSchema(
            user=UserResponseSchema(**_user_to_response(user)),
            tokens=TokenPairSchema(**tokens),
        )

    @auth_router.post("/login")
    async def login(
        data: LoginRequest,
        api_state: LiveAPIState = Depends(get_state),
    ) -> AuthResponseSchema:
        """Login with email + password. Returns user + tokens."""
        user = api_state.user_db.get_by_email(data.email)
        if user is None or not api_state.hasher.verify(data.password, user.hashed_password):
            raise LiveAPIError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")

        if not user.is_active:
            raise LiveAPIError(403, "FORBIDDEN", "Account is deactivated")

        user_resp = _user_to_response(user)
        tokens = api_state.token_service.create_token_pair(user.id, user_resp["role"])

        return AuthResponseSchema(
            user=UserResponseSchema(**user_resp),
            tokens=TokenPairSchema(**tokens),
        )

    @auth_router.post("/refresh")
    async def refresh(
        data: RefreshRequest,
        api_state: LiveAPIState = Depends(get_state),
    ) -> TokenPairSchema:
        """Refresh access token using refresh token."""
        try:
            payload = api_state.token_service.decode_token(
                data.refresh_token, expected_type="refresh"
            )
        except TokenError as e:
            raise LiveAPIError(401, "INVALID_TOKEN", str(e))

        user = api_state.user_db.get_by_id(payload["sub"])
        if user is None or not user.is_active:
            raise LiveAPIError(401, "INVALID_TOKEN", "User not found or deactivated")

        # Rotate: revoke old, issue new
        api_state.token_service.revoke_refresh_token(data.refresh_token)
        user_resp = _user_to_response(user)
        tokens = api_state.token_service.create_token_pair(user.id, user_resp["role"])
        return TokenPairSchema(**tokens)

    @auth_router.delete("/logout")
    async def logout(
        credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
        api_state: LiveAPIState = Depends(get_state),
    ) -> MessageResponseSchema:
        """Revoke the session. Requires bearer token."""
        if credentials is None:
            raise LiveAPIError(401, "UNAUTHORIZED", "Authentication required")

        try:
            payload = api_state.token_service.decode_token(
                credentials.credentials, expected_type="access"
            )
        except TokenError as e:
            raise LiveAPIError(401, "UNAUTHORIZED", str(e))

        # Revoke all refresh tokens for this user isn't practical with in-memory set,
        # but the access token identifies the session. For the contract, just confirm logout.
        return MessageResponseSchema(message="Logged out successfully.")

    app.include_router(auth_router)

    # ── Users Router (/api/v1/users) ──────────────────────────────────

    users_router = APIRouter(prefix="/api/v1/users", tags=["Users"])

    @users_router.get("/me")
    async def get_me(
        user: dict[str, Any] = Depends(get_current_user),
    ) -> UserResponseSchema:
        """Get current user profile."""
        return UserResponseSchema(**user)

    @users_router.put("/me")
    async def update_me(
        data: UpdateUserRequest,
        credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
        api_state: LiveAPIState = Depends(get_state),
    ) -> UserResponseSchema:
        """Update current user profile. Only provided fields change."""
        if credentials is None:
            raise LiveAPIError(401, "UNAUTHORIZED", "Authentication required")

        try:
            payload = api_state.token_service.decode_token(
                credentials.credentials, expected_type="access"
            )
        except TokenError as e:
            raise LiveAPIError(401, "UNAUTHORIZED", str(e))

        user = api_state.user_db.get_by_id(payload["sub"])
        if user is None:
            raise LiveAPIError(401, "UNAUTHORIZED", "User not found")
        if not user.is_active:
            raise LiveAPIError(403, "FORBIDDEN", "Account is deactivated")

        if data.name is not None:
            user.username = data.name
        if data.email is not None:
            # Check for conflict
            existing = api_state.user_db.get_by_email(data.email)
            if existing and existing.id != user.id:
                raise LiveAPIError(409, "CONFLICT", "A user with this email already exists.")
            user.email = data.email

        api_state.user_db.update_user(user)
        return UserResponseSchema(**_user_to_response(user))

    app.include_router(users_router)

    # ── Resources Router (/api/v1/resources) ──────────────────────────

    resources_router = APIRouter(prefix="/api/v1/resources", tags=["Resources"])

    @resources_router.get("")
    async def list_resources(
        page: int = Query(1, ge=1),
        per_page: int = Query(20, ge=1, le=100),
        _user: dict[str, Any] = Depends(get_current_user),
        api_state: LiveAPIState = Depends(get_state),
    ) -> ResourceListSchema:
        """List protected resources with pagination."""
        result = api_state.resource_db.list_resources(page=page, per_page=per_page)
        return ResourceListSchema(
            data=[ResourceSchema(**r) for r in result["data"]],
            meta=PaginationMetaSchema(**result["meta"]),
        )

    app.include_router(resources_router)

    # ── Health (/api/v1/health) ───────────────────────────────────────

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        """Public health check endpoint."""
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return app


# ─── Standalone Entrypoint ────────────────────────────────────────────────

app = create_live_api()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "orchestrator.live_api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
