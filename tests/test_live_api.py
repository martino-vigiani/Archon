"""
Integration tests for the live API (orchestrator/live_api.py).

Tests the full contract-compliant API surface:
- POST /api/v1/auth/register  → AuthResponse (user + tokens)
- POST /api/v1/auth/login     → AuthResponse (user + tokens)
- POST /api/v1/auth/refresh   → TokenPair
- DELETE /api/v1/auth/logout   → MessageResponse
- GET /api/v1/users/me         → UserResponse
- PUT /api/v1/users/me         → UserResponse
- GET /api/v1/resources        → ResourceList
- GET /api/v1/health           → {status, timestamp}

All responses match the OpenAPI spec in .orchestra/contracts/api-openapi.yaml
and T1's APIClient SDK in orchestrator/api_client.py.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.auth.config import AuthConfig
from orchestrator.live_api import create_live_api


# ─── Fixtures ─────────────────────────────────────────────────────────────


def _create_test_app() -> AsyncClient:
    """Create a fresh live API app with in-memory database."""
    config = AuthConfig(
        secret_key="live-api-test-secret-key-min-32bytes",
        access_token_expire_minutes=30,
        refresh_token_expire_days=7,
        db_path=":memory:",
        min_password_length=8,
    )
    app = create_live_api(auth_config=config, db_path=":memory:")
    return app


@pytest.fixture
async def client():
    """Async HTTP client for the live API."""
    app = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ─── Helpers ──────────────────────────────────────────────────────────────


async def _register(
    client: AsyncClient,
    email: str = "alice@example.com",
    password: str = "SecurePass123!",
    name: str = "Alice",
) -> dict:
    resp = await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": password,
        "name": name,
    })
    return resp.json()


async def _login(
    client: AsyncClient,
    email: str = "alice@example.com",
    password: str = "SecurePass123!",
) -> dict:
    resp = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": password,
    })
    return resp.json()


async def _register_and_login(
    client: AsyncClient,
    email: str = "alice@example.com",
    password: str = "SecurePass123!",
    name: str = "Alice",
) -> dict:
    await _register(client, email, password, name)
    return await _login(client, email, password)


def _auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


# ═══════════════════════════════════════════════════════════════════════════
# Health
# ═══════════════════════════════════════════════════════════════════════════


class TestHealth:
    async def test_health_returns_healthy(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    async def test_health_no_auth_required(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════════════════════


class TestRegister:
    async def test_successful_registration(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/auth/register", json={
            "email": "alice@example.com",
            "password": "SecurePass123!",
            "name": "Alice",
        })
        assert resp.status_code == 201
        data = resp.json()

        # AuthResponse shape: { user: {...}, tokens: {...} }
        assert "user" in data
        assert "tokens" in data

        user = data["user"]
        assert user["email"] == "alice@example.com"
        assert user["name"] == "Alice"
        assert "id" in user
        assert "created_at" in user
        assert "password" not in user
        assert "hashed_password" not in user

        tokens = data["tokens"]
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"
        assert tokens["expires_in"] > 0

    async def test_first_user_gets_admin(self, client: AsyncClient) -> None:
        data = await _register(client)
        assert data["user"]["role"] == "admin"

    async def test_second_user_gets_user_role(self, client: AsyncClient) -> None:
        await _register(client, "first@example.com", "Pass12345!", "First")
        data = await _register(client, "second@example.com", "Pass12345!", "Second")
        assert data["user"]["role"] == "user"

    async def test_duplicate_email_rejected(self, client: AsyncClient) -> None:
        await _register(client)
        resp = await client.post("/api/v1/auth/register", json={
            "email": "alice@example.com",
            "password": "AnotherPass123!",
            "name": "Alice2",
        })
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    async def test_invalid_email_rejected(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/auth/register", json={
            "email": "not-an-email",
            "password": "SecurePass123!",
            "name": "Test",
        })
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_short_password_rejected(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/auth/register", json={
            "email": "test@example.com",
            "password": "short",
            "name": "Test",
        })
        assert resp.status_code == 422

    async def test_missing_name_rejected(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/auth/register", json={
            "email": "test@example.com",
            "password": "SecurePass123!",
        })
        assert resp.status_code == 422

    async def test_empty_body_rejected(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/auth/register", content=b"")
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Login
# ═══════════════════════════════════════════════════════════════════════════


class TestLogin:
    async def test_successful_login(self, client: AsyncClient) -> None:
        await _register(client)
        resp = await client.post("/api/v1/auth/login", json={
            "email": "alice@example.com",
            "password": "SecurePass123!",
        })
        assert resp.status_code == 200
        data = resp.json()

        # AuthResponse shape
        assert "user" in data
        assert "tokens" in data
        assert data["user"]["email"] == "alice@example.com"
        assert data["tokens"]["token_type"] == "bearer"

    async def test_wrong_password_rejected(self, client: AsyncClient) -> None:
        await _register(client)
        resp = await client.post("/api/v1/auth/login", json={
            "email": "alice@example.com",
            "password": "WrongPassword123!",
        })
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"

    async def test_nonexistent_email_rejected(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/auth/login", json={
            "email": "ghost@example.com",
            "password": "SecurePass123!",
        })
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"

    async def test_same_error_for_wrong_email_and_password(
        self, client: AsyncClient,
    ) -> None:
        """Prevents user enumeration."""
        await _register(client)
        r1 = await client.post("/api/v1/auth/login", json={
            "email": "wrong@example.com",
            "password": "SecurePass123!",
        })
        r2 = await client.post("/api/v1/auth/login", json={
            "email": "alice@example.com",
            "password": "WrongPass123!",
        })
        assert r1.json()["error"]["message"] == r2.json()["error"]["message"]

    async def test_login_tokens_work_on_protected_endpoints(
        self, client: AsyncClient,
    ) -> None:
        auth = await _register_and_login(client)
        resp = await client.get(
            "/api/v1/users/me",
            headers=_auth_header(auth["tokens"]["access_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "alice@example.com"


# ═══════════════════════════════════════════════════════════════════════════
# Token Refresh
# ═══════════════════════════════════════════════════════════════════════════


class TestRefresh:
    async def test_successful_refresh(self, client: AsyncClient) -> None:
        auth = await _register_and_login(client)
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": auth["tokens"]["refresh_token"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_old_refresh_token_revoked_after_rotation(
        self, client: AsyncClient,
    ) -> None:
        auth = await _register_and_login(client)
        old_refresh = auth["tokens"]["refresh_token"]

        # Use the refresh token
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": old_refresh,
        })
        assert resp.status_code == 200

        # Old refresh token should now fail
        resp2 = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": old_refresh,
        })
        assert resp2.status_code == 401

    async def test_access_token_as_refresh_rejected(
        self, client: AsyncClient,
    ) -> None:
        auth = await _register_and_login(client)
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": auth["tokens"]["access_token"],
        })
        assert resp.status_code == 401

    async def test_invalid_refresh_token_rejected(
        self, client: AsyncClient,
    ) -> None:
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": "not.a.valid.token",
        })
        assert resp.status_code == 401

    async def test_new_tokens_work(self, client: AsyncClient) -> None:
        auth = await _register_and_login(client)
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": auth["tokens"]["refresh_token"],
        })
        new_tokens = resp.json()

        me_resp = await client.get(
            "/api/v1/users/me",
            headers=_auth_header(new_tokens["access_token"]),
        )
        assert me_resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Logout
# ═══════════════════════════════════════════════════════════════════════════


class TestLogout:
    async def test_successful_logout(self, client: AsyncClient) -> None:
        auth = await _register_and_login(client)
        resp = await client.delete(
            "/api/v1/auth/logout",
            headers=_auth_header(auth["tokens"]["access_token"]),
        )
        assert resp.status_code == 200
        assert "logged out" in resp.json()["message"].lower()

    async def test_logout_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.delete("/api/v1/auth/logout")
        assert resp.status_code == 401

    async def test_logout_with_invalid_token(self, client: AsyncClient) -> None:
        resp = await client.delete(
            "/api/v1/auth/logout",
            headers=_auth_header("invalid.token.here"),
        )
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# GET /users/me
# ═══════════════════════════════════════════════════════════════════════════


class TestGetMe:
    async def test_get_me_returns_user(self, client: AsyncClient) -> None:
        auth = await _register_and_login(client)
        resp = await client.get(
            "/api/v1/users/me",
            headers=_auth_header(auth["tokens"]["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "alice@example.com"
        assert data["name"] == "Alice"
        assert "id" in data
        assert "created_at" in data
        assert "hashed_password" not in data

    async def test_get_me_without_token(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/users/me")
        assert resp.status_code == 401

    async def test_get_me_with_invalid_token(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/api/v1/users/me",
            headers=_auth_header("totally.invalid.token"),
        )
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# PUT /users/me
# ═══════════════════════════════════════════════════════════════════════════


class TestUpdateMe:
    async def test_update_name(self, client: AsyncClient) -> None:
        auth = await _register_and_login(client)
        resp = await client.put(
            "/api/v1/users/me",
            json={"name": "Alice Updated"},
            headers=_auth_header(auth["tokens"]["access_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Alice Updated"

    async def test_update_email(self, client: AsyncClient) -> None:
        auth = await _register_and_login(client)
        resp = await client.put(
            "/api/v1/users/me",
            json={"email": "newalice@example.com"},
            headers=_auth_header(auth["tokens"]["access_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "newalice@example.com"

    async def test_update_both(self, client: AsyncClient) -> None:
        auth = await _register_and_login(client)
        resp = await client.put(
            "/api/v1/users/me",
            json={"name": "New Name", "email": "new@example.com"},
            headers=_auth_header(auth["tokens"]["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["email"] == "new@example.com"

    async def test_update_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.put("/api/v1/users/me", json={"name": "X"})
        assert resp.status_code == 401

    async def test_email_conflict_rejected(self, client: AsyncClient) -> None:
        await _register(client, "alice@example.com", "Pass12345!", "Alice")
        auth = await _register_and_login(
            client, "bob@example.com", "Pass12345!", "Bob"
        )
        resp = await client.put(
            "/api/v1/users/me",
            json={"email": "alice@example.com"},
            headers=_auth_header(auth["tokens"]["access_token"]),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"


# ═══════════════════════════════════════════════════════════════════════════
# Resources
# ═══════════════════════════════════════════════════════════════════════════


class TestResources:
    async def test_list_resources(self, client: AsyncClient) -> None:
        auth = await _register_and_login(client)
        resp = await client.get(
            "/api/v1/resources",
            headers=_auth_header(auth["tokens"]["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "meta" in data
        assert isinstance(data["data"], list)
        assert data["meta"]["page"] == 1
        assert data["meta"]["per_page"] == 20

    async def test_resources_have_correct_shape(self, client: AsyncClient) -> None:
        auth = await _register_and_login(client)
        resp = await client.get(
            "/api/v1/resources",
            headers=_auth_header(auth["tokens"]["access_token"]),
        )
        data = resp.json()
        assert len(data["data"]) > 0

        resource = data["data"][0]
        assert "id" in resource
        assert "title" in resource
        assert "content" in resource
        assert "owner_id" in resource
        assert "created_at" in resource

    async def test_resources_require_auth(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/resources")
        assert resp.status_code == 401

    async def test_pagination_params(self, client: AsyncClient) -> None:
        auth = await _register_and_login(client)
        resp = await client.get(
            "/api/v1/resources?page=1&per_page=2",
            headers=_auth_header(auth["tokens"]["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["per_page"] == 2
        assert len(data["data"]) <= 2

    async def test_pagination_total(self, client: AsyncClient) -> None:
        auth = await _register_and_login(client)
        resp = await client.get(
            "/api/v1/resources",
            headers=_auth_header(auth["tokens"]["access_token"]),
        )
        data = resp.json()
        assert data["meta"]["total"] == 5  # 5 seed resources
        assert data["meta"]["total_pages"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# Error Format
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorFormat:
    """All errors must follow { error: { code, message } } contract."""

    async def test_auth_error_format(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/auth/login", json={
            "email": "x@x.com",
            "password": "wrong",
        })
        data = resp.json()
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]

    async def test_validation_error_format(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/auth/register", json={})
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "details" in data["error"]

    async def test_unauthorized_error_format(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/users/me")
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "UNAUTHORIZED"


# ═══════════════════════════════════════════════════════════════════════════
# Full Lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestFullLifecycle:
    async def test_register_login_use_refresh_logout(
        self, client: AsyncClient,
    ) -> None:
        """Complete happy path lifecycle."""
        # 1. Register
        reg = await client.post("/api/v1/auth/register", json={
            "email": "lifecycle@example.com",
            "password": "SecurePass123!",
            "name": "Lifecycle User",
        })
        assert reg.status_code == 201
        reg_tokens = reg.json()["tokens"]

        # 2. Use access token
        me = await client.get(
            "/api/v1/users/me",
            headers=_auth_header(reg_tokens["access_token"]),
        )
        assert me.status_code == 200
        assert me.json()["name"] == "Lifecycle User"

        # 3. Login
        login = await client.post("/api/v1/auth/login", json={
            "email": "lifecycle@example.com",
            "password": "SecurePass123!",
        })
        assert login.status_code == 200
        login_tokens = login.json()["tokens"]

        # 4. List resources
        resources = await client.get(
            "/api/v1/resources",
            headers=_auth_header(login_tokens["access_token"]),
        )
        assert resources.status_code == 200
        assert len(resources.json()["data"]) > 0

        # 5. Refresh
        refresh = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": login_tokens["refresh_token"],
        })
        assert refresh.status_code == 200
        new_tokens = refresh.json()

        # 6. Update profile
        update = await client.put(
            "/api/v1/users/me",
            json={"name": "Updated Name"},
            headers=_auth_header(new_tokens["access_token"]),
        )
        assert update.status_code == 200
        assert update.json()["name"] == "Updated Name"

        # 7. Logout
        logout = await client.delete(
            "/api/v1/auth/logout",
            headers=_auth_header(new_tokens["access_token"]),
        )
        assert logout.status_code == 200

    async def test_multiple_users_isolated(self, client: AsyncClient) -> None:
        auth_a = await _register_and_login(
            client, "alice@example.com", "Pass12345!", "Alice"
        )
        auth_b = await _register_and_login(
            client, "bob@example.com", "Pass12345!", "Bob"
        )

        me_a = await client.get(
            "/api/v1/users/me",
            headers=_auth_header(auth_a["tokens"]["access_token"]),
        )
        me_b = await client.get(
            "/api/v1/users/me",
            headers=_auth_header(auth_b["tokens"]["access_token"]),
        )

        assert me_a.json()["name"] == "Alice"
        assert me_b.json()["name"] == "Bob"
