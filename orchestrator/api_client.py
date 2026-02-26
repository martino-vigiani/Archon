"""API Client SDK - Typed wrapper for the Archon REST API.

Matches the interface contracts defined in .orchestra/contracts/RESTAPIContract.json
and .orchestra/contracts/api-openapi.yaml. Works with both the real backend (T2)
and built-in mock responses for standalone development.

Usage:
    client = APIClient("http://localhost:8000/api/v1")
    auth = await client.register("alice@example.com", "s3cur3P@ss!", "Alice")
    items = await client.list_resources(page=1, per_page=20)

    # Or with mock mode (no backend needed):
    client = APIClient.mock()
    auth = await client.login("alice@example.com", "password")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

import httpx


# ─── Response Models ─────────────────────────────────────────────────


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


@dataclass(frozen=True)
class UserResponse:
    """User profile data returned by the API."""

    id: str
    email: str
    name: str
    role: UserRole
    created_at: str
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserResponse:
        return cls(
            id=data["id"],
            email=data["email"],
            name=data["name"],
            role=UserRole(data.get("role", "user")),
            created_at=data["created_at"],
            updated_at=data.get("updated_at"),
        )


@dataclass(frozen=True)
class TokenPair:
    """Access + refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenPair:
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_type=data.get("token_type", "bearer"),
            expires_in=data.get("expires_in", 900),
        )


@dataclass(frozen=True)
class AuthResponse:
    """Combined user + tokens returned by register/login."""

    user: UserResponse
    tokens: TokenPair

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthResponse:
        return cls(
            user=UserResponse.from_dict(data["user"]),
            tokens=TokenPair.from_dict(data["tokens"]),
        )


@dataclass(frozen=True)
class Resource:
    """Protected resource item."""

    id: str
    title: str
    content: str
    owner_id: str
    created_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Resource:
        return cls(
            id=data["id"],
            title=data["title"],
            content=data["content"],
            owner_id=data["owner_id"],
            created_at=data["created_at"],
        )


@dataclass(frozen=True)
class PaginationMeta:
    """Pagination metadata."""

    page: int
    per_page: int
    total: int
    total_pages: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaginationMeta:
        return cls(
            page=data["page"],
            per_page=data["per_page"],
            total=data["total"],
            total_pages=data["total_pages"],
        )


@dataclass(frozen=True)
class ResourceList:
    """Paginated list of resources."""

    data: list[Resource]
    meta: PaginationMeta

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResourceList:
        return cls(
            data=[Resource.from_dict(r) for r in data["data"]],
            meta=PaginationMeta.from_dict(data["meta"]),
        )


@dataclass(frozen=True)
class FieldError:
    """Per-field validation error."""

    field: str
    message: str


@dataclass(frozen=True)
class APIError:
    """Structured error from the API."""

    code: str
    message: str
    status_code: int
    details: list[FieldError] = field(default_factory=list)

    @classmethod
    def from_response(cls, status_code: int, data: dict[str, Any]) -> APIError:
        error_data = data.get("error", data)
        details = [
            FieldError(field=d["field"], message=d["message"])
            for d in error_data.get("details", [])
        ]
        return cls(
            code=error_data.get("code", "UNKNOWN"),
            message=error_data.get("message", "Unknown error"),
            status_code=status_code,
            details=details,
        )


class APIClientError(Exception):
    """Raised when the API returns an error response."""

    def __init__(self, error: APIError):
        self.error = error
        super().__init__(f"[{error.code}] {error.message}")


# ─── Mock Data ───────────────────────────────────────────────────────


def _mock_users() -> list[dict[str, Any]]:
    """Generate realistic mock user data."""
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "email": "alice@example.com",
            "name": "Alice Chen",
            "role": "admin",
            "created_at": "2026-01-15T08:00:00Z",
            "updated_at": "2026-02-19T14:30:00Z",
        },
        {
            "id": "660e8400-e29b-41d4-a716-446655440001",
            "email": "bob@example.com",
            "name": "Bob Martinez",
            "role": "user",
            "created_at": "2026-01-20T10:15:00Z",
            "updated_at": "2026-02-18T09:00:00Z",
        },
        {
            "id": "770e8400-e29b-41d4-a716-446655440002",
            "email": "carol@example.com",
            "name": "Carol Nakamura",
            "role": "user",
            "created_at": "2026-02-01T16:45:00Z",
            "updated_at": now,
        },
        {
            "id": "880e8400-e29b-41d4-a716-446655440003",
            "email": "dave@example.com",
            "name": "Dave Okonkwo",
            "role": "user",
            "created_at": "2026-02-10T11:30:00Z",
            "updated_at": now,
        },
        {
            "id": "990e8400-e29b-41d4-a716-446655440004",
            "email": "eve@example.com",
            "name": "Eve Rosenberg",
            "role": "user",
            "created_at": "2026-02-15T07:20:00Z",
            "updated_at": now,
        },
    ]


def _mock_resources() -> list[dict[str, Any]]:
    """Generate mock resource data."""
    return [
        {
            "id": f"res-{uuid4().hex[:8]}",
            "title": title,
            "content": content,
            "owner_id": "550e8400-e29b-41d4-a716-446655440000",
            "created_at": "2026-02-18T12:00:00Z",
        }
        for title, content in [
            ("API Design Notes", "RESTful patterns and endpoint conventions."),
            ("Sprint Retro", "What went well, what to improve."),
            ("Architecture Decision Record", "Chose FastAPI over Flask for async."),
            ("Deployment Checklist", "Pre-launch verification steps."),
            ("Performance Baseline", "Initial load test results and metrics."),
        ]
    ]


def _mock_token_pair() -> dict[str, Any]:
    """Generate a mock token pair."""
    return {
        "access_token": f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.mock.{uuid4().hex[:16]}",
        "refresh_token": f"refresh.{uuid4().hex}",
        "token_type": "bearer",
        "expires_in": 900,
    }


# ─── Client ──────────────────────────────────────────────────────────


class APIClient:
    """Typed API client for the Archon REST API.

    Supports both real HTTP calls and mock mode for standalone development.
    Automatically manages access tokens and handles token refresh.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000/api/v1",
        *,
        use_mock: bool = False,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.use_mock = use_mock
        self._tokens: TokenPair | None = None
        self._token_issued_at: float = 0
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    @classmethod
    def mock(cls) -> APIClient:
        """Create a client in mock mode (no backend needed)."""
        return cls(use_mock=True)

    @property
    def is_authenticated(self) -> bool:
        """Check if we have a valid (non-expired) access token."""
        if self._tokens is None:
            return False
        elapsed = time.time() - self._token_issued_at
        return elapsed < self._tokens.expires_in

    @property
    def access_token(self) -> str | None:
        """Current access token, or None if not authenticated."""
        return self._tokens.access_token if self._tokens else None

    def _auth_headers(self) -> dict[str, str]:
        """Build authorization headers."""
        if self._tokens:
            return {"Authorization": f"Bearer {self._tokens.access_token}"}
        return {}

    def _store_tokens(self, tokens: TokenPair) -> None:
        """Store tokens and record issue time."""
        self._tokens = tokens
        self._token_issued_at = time.time()

    # ─── Auth Endpoints ────────────────────────────────────────────

    async def register(
        self, email: str, password: str, name: str
    ) -> AuthResponse:
        """Register a new user account.

        Returns user profile + token pair on success.
        Raises APIClientError on 409 (email taken) or 422 (validation).
        """
        if self.use_mock:
            user = _mock_users()[0] | {"email": email, "name": name, "id": uuid4().hex}
            tokens = _mock_token_pair()
            result = AuthResponse.from_dict({"user": user, "tokens": tokens})
            self._store_tokens(result.tokens)
            return result

        resp = await self._http.post(
            "/auth/register",
            json={"email": email, "password": password, "name": name},
        )
        return self._handle_auth_response(resp, expected_status=201)

    async def login(self, email: str, password: str) -> AuthResponse:
        """Log in with email and password.

        Returns user profile + token pair.
        Raises APIClientError on 401 (invalid credentials).
        """
        if self.use_mock:
            users = _mock_users()
            match = next((u for u in users if u["email"] == email), users[0])
            tokens = _mock_token_pair()
            result = AuthResponse.from_dict({"user": match, "tokens": tokens})
            self._store_tokens(result.tokens)
            return result

        resp = await self._http.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        return self._handle_auth_response(resp)

    async def refresh(self) -> TokenPair:
        """Refresh the access token using the stored refresh token.

        Returns a new token pair. Old refresh token is invalidated.
        """
        if self._tokens is None:
            raise APIClientError(
                APIError(code="NO_TOKEN", message="No refresh token available", status_code=0)
            )

        if self.use_mock:
            tokens = TokenPair.from_dict(_mock_token_pair())
            self._store_tokens(tokens)
            return tokens

        resp = await self._http.post(
            "/auth/refresh",
            json={"refresh_token": self._tokens.refresh_token},
        )
        data = self._check_response(resp)
        tokens = TokenPair.from_dict(data)
        self._store_tokens(tokens)
        return tokens

    async def logout(self) -> str:
        """Log out and revoke the refresh token.

        Returns success message.
        """
        if self.use_mock:
            self._tokens = None
            return "Logged out successfully."

        data = await self._request_with_retry("DELETE", "/auth/logout")
        self._tokens = None
        return data.get("message", "Logged out")

    # ─── User Endpoints ────────────────────────────────────────────

    async def get_me(self) -> UserResponse:
        """Get the current authenticated user's profile."""
        if self.use_mock:
            return UserResponse.from_dict(_mock_users()[0])

        data = await self._request_with_retry("GET", "/users/me")
        return UserResponse.from_dict(data)

    async def update_me(
        self, *, name: str | None = None, email: str | None = None
    ) -> UserResponse:
        """Update the current user's profile. Only provided fields change."""
        body: dict[str, str] = {}
        if name is not None:
            body["name"] = name
        if email is not None:
            body["email"] = email

        if self.use_mock:
            user = _mock_users()[0] | body
            return UserResponse.from_dict(user)

        data = await self._request_with_retry("PUT", "/users/me", json=body)
        return UserResponse.from_dict(data)

    # ─── Admin User Endpoints ─────────────────────────────────────

    async def list_users(
        self, *, page: int = 1, per_page: int = 20
    ) -> dict[str, Any]:
        """List all users with pagination. Admin only.

        Returns { data: [UserResponse], meta: PaginationMeta }.
        Raises APIClientError on 403 (not admin).
        """
        if self.use_mock:
            users = _mock_users()
            start = (page - 1) * per_page
            page_data = users[start : start + per_page]
            return {
                "data": [UserResponse.from_dict(u) for u in page_data],
                "meta": PaginationMeta.from_dict({
                    "page": page,
                    "per_page": per_page,
                    "total": len(users),
                    "total_pages": max(1, -(-len(users) // per_page)),
                }),
            }

        data = await self._request_with_retry(
            "GET", "/users", params={"page": page, "per_page": per_page}
        )
        return {
            "data": [UserResponse.from_dict(u) for u in data["data"]],
            "meta": PaginationMeta.from_dict(data["meta"]),
        }

    async def update_user(
        self,
        user_id: str,
        *,
        name: str | None = None,
        email: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> UserResponse:
        """Update any user by ID. Admin only.

        Raises APIClientError on 403 (not admin), 404 (not found),
        400 (self-demotion), 409 (email conflict).
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if email is not None:
            body["email"] = email
        if role is not None:
            body["role"] = role
        if is_active is not None:
            body["is_active"] = is_active

        if self.use_mock:
            users = _mock_users()
            match = next((u for u in users if u["id"] == user_id), users[0])
            return UserResponse.from_dict(match | body)

        data = await self._request_with_retry("PUT", f"/users/{user_id}", json=body)
        return UserResponse.from_dict(data)

    async def delete_user(self, user_id: str) -> str:
        """Delete a user by ID. Admin only.

        Returns success message.
        Raises APIClientError on 403 (not admin), 404 (not found),
        400 (self-deletion).
        """
        if self.use_mock:
            return "User deleted successfully."

        data = await self._request_with_retry("DELETE", f"/users/{user_id}")
        return data.get("message", "User deleted")

    # ─── Resource Endpoints ────────────────────────────────────────

    async def list_resources(
        self, *, page: int = 1, per_page: int = 20
    ) -> ResourceList:
        """List protected resources with pagination."""
        if self.use_mock:
            resources = _mock_resources()
            start = (page - 1) * per_page
            page_data = resources[start : start + per_page]
            return ResourceList.from_dict(
                {
                    "data": page_data,
                    "meta": {
                        "page": page,
                        "per_page": per_page,
                        "total": len(resources),
                        "total_pages": max(1, -(-len(resources) // per_page)),
                    },
                }
            )

        data = await self._request_with_retry(
            "GET", "/resources", params={"page": page, "per_page": per_page}
        )
        return ResourceList.from_dict(data)

    # ─── Health ────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        """Check API health status."""
        if self.use_mock:
            return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

        resp = await self._http.get("/health")
        return self._check_response(resp)

    # ─── Helpers ───────────────────────────────────────────────────

    def _check_response(self, resp: httpx.Response) -> dict[str, Any]:
        """Check response status and return parsed JSON, or raise APIClientError."""
        data = resp.json()
        if resp.status_code >= 400:
            raise APIClientError(APIError.from_response(resp.status_code, data))
        return data

    def _handle_auth_response(
        self, resp: httpx.Response, expected_status: int = 200
    ) -> AuthResponse:
        """Handle register/login response: parse, store tokens, return."""
        data = self._check_response(resp)
        result = AuthResponse.from_dict(data)
        self._store_tokens(result.tokens)
        return result

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request with automatic 401 retry via token refresh.

        On 401, attempts to refresh the access token and retries the request once.
        Raises APIClientError if refresh also fails or retry still returns an error.
        """
        kwargs: dict[str, Any] = {"headers": self._auth_headers()}
        if json is not None:
            kwargs["json"] = json
        if params is not None:
            kwargs["params"] = params

        resp = await self._http.request(method, path, **kwargs)

        if resp.status_code == 401 and self._tokens and self._tokens.refresh_token:
            try:
                await self.refresh()
            except APIClientError:
                raise APIClientError(
                    APIError.from_response(resp.status_code, resp.json())
                )

            kwargs["headers"] = self._auth_headers()
            resp = await self._http.request(method, path, **kwargs)

        return self._check_response(resp)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> APIClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ─── Introspection (for admin UI) ──────────────────────────────

    def get_token_status(self) -> dict[str, Any]:
        """Get current token status for display purposes."""
        if self._tokens is None:
            return {"authenticated": False}

        elapsed = time.time() - self._token_issued_at
        remaining = max(0, self._tokens.expires_in - elapsed)
        return {
            "authenticated": True,
            "token_type": self._tokens.token_type,
            "expires_in": int(remaining),
            "total_ttl": self._tokens.expires_in,
            "has_refresh": bool(self._tokens.refresh_token),
        }

    def get_mock_data(self) -> dict[str, Any]:
        """Export all mock data for the admin UI."""
        resources = _mock_resources()
        return {
            "users": _mock_users(),
            "resources": resources,
            "token": _mock_token_pair(),
            "health": {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()},
            "pagination": {
                "page": 1,
                "per_page": 20,
                "total": len(resources),
                "total_pages": 1,
            },
        }
