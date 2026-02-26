"""
HTTP integration tests for the auth module.

Tests the full auth lifecycle through FastAPI's test client:
- Registration (success, duplicate rejection, validation)
- Login (valid/invalid credentials, inactive user)
- Token refresh (rotation, revoked tokens, wrong token type)
- Protected endpoints (with/without token, expired token)
- Logout (token invalidation, post-logout behavior)
- Role-based access control (admin-only endpoints)
- Token expiration edge cases
"""

import time

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from orchestrator.auth.config import AuthConfig
from orchestrator.auth.database import UserDatabase
from orchestrator.auth.error_handlers import register_error_handlers
from orchestrator.auth.routes import create_auth_router
from orchestrator.auth.tokens import TokenService


# ---------------------------------------------------------------------------
# Test App & Fixtures
# ---------------------------------------------------------------------------


def _create_test_app(
    *,
    access_token_expire_minutes: int = 30,
    refresh_token_expire_days: int = 7,
) -> tuple[FastAPI, AuthConfig, UserDatabase, TokenService]:
    """Create a fresh FastAPI app with in-memory auth for each test."""
    config = AuthConfig(
        secret_key="integration-test-secret-key-fixed",
        access_token_expire_minutes=access_token_expire_minutes,
        refresh_token_expire_days=refresh_token_expire_days,
        db_path=":memory:",
        min_password_length=8,
    )
    db = UserDatabase(":memory:")
    token_service = TokenService(config)
    app = FastAPI()
    register_error_handlers(app)
    router = create_auth_router(config=config, db=db, token_service=token_service)
    app.include_router(router)
    return app, config, db, token_service


@pytest.fixture
async def auth_client():
    """Async HTTP client with a fresh auth app."""
    app, config, db, token_service = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def auth_env():
    """Full test environment: client + db + token_service for deeper checks."""
    app, config, db, token_service = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {
            "client": client,
            "config": config,
            "db": db,
            "token_service": token_service,
        }


async def _register_user(
    client: AsyncClient,
    username: str = "testuser",
    email: str = "test@example.com",
    password: str = "SecurePass123",
) -> dict:
    """Helper: register a user and return the response JSON."""
    resp = await client.post("/auth/register", json={
        "username": username,
        "email": email,
        "password": password,
    })
    return resp.json()


async def _login_user(
    client: AsyncClient,
    username: str = "testuser",
    password: str = "SecurePass123",
) -> dict:
    """Helper: login and return the response JSON (includes tokens)."""
    resp = await client.post("/auth/login", json={
        "username": username,
        "password": password,
    })
    return resp.json()


async def _register_and_login(
    client: AsyncClient,
    username: str = "testuser",
    email: str = "test@example.com",
    password: str = "SecurePass123",
) -> dict:
    """Helper: register then login, return token response."""
    await _register_user(client, username, email, password)
    return await _login_user(client, username, password)


def _auth_header(access_token: str) -> dict[str, str]:
    """Helper: build Authorization header."""
    return {"Authorization": f"Bearer {access_token}"}


# ===========================================================================
# Registration Tests
# ===========================================================================


class TestRegistration:
    """POST /auth/register"""

    async def test_successful_registration(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.post("/auth/register", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "SecurePass123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "newuser"
        assert data["email"] == "new@example.com"
        assert data["is_active"] is True
        assert "id" in data
        # Password must never appear in response
        assert "password" not in data
        assert "hashed_password" not in data

    async def test_first_user_gets_admin_role(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.post("/auth/register", json={
            "username": "firstuser",
            "email": "first@example.com",
            "password": "SecurePass123",
        })
        assert resp.status_code == 201
        assert resp.json()["role"] == "admin"

    async def test_second_user_gets_viewer_role(self, auth_client: AsyncClient) -> None:
        await _register_user(auth_client, "first", "first@example.com")
        resp = await auth_client.post("/auth/register", json={
            "username": "second",
            "email": "second@example.com",
            "password": "SecurePass123",
        })
        assert resp.status_code == 201
        assert resp.json()["role"] == "viewer"

    async def test_duplicate_username_rejected(self, auth_client: AsyncClient) -> None:
        await _register_user(auth_client, "taken", "a@example.com")
        resp = await auth_client.post("/auth/register", json={
            "username": "taken",
            "email": "b@example.com",
            "password": "SecurePass123",
        })
        assert resp.status_code == 409
        assert "already exists" in resp.json()["error"]["message"]

    async def test_duplicate_email_rejected(self, auth_client: AsyncClient) -> None:
        await _register_user(auth_client, "user1", "same@example.com")
        resp = await auth_client.post("/auth/register", json={
            "username": "user2",
            "email": "same@example.com",
            "password": "SecurePass123",
        })
        assert resp.status_code == 409
        assert "already exists" in resp.json()["error"]["message"]

    async def test_username_too_short_rejected(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.post("/auth/register", json={
            "username": "ab",
            "email": "ab@example.com",
            "password": "SecurePass123",
        })
        assert resp.status_code == 422

    async def test_invalid_email_rejected(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.post("/auth/register", json={
            "username": "validuser",
            "email": "not-an-email",
            "password": "SecurePass123",
        })
        assert resp.status_code == 422

    async def test_password_too_short_rejected(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.post("/auth/register", json={
            "username": "validuser",
            "email": "valid@example.com",
            "password": "short",
        })
        # Pydantic catches min_length=8 before the route handler
        assert resp.status_code == 422

    async def test_username_normalized_to_lowercase(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.post("/auth/register", json={
            "username": "MyUser",
            "email": "my@example.com",
            "password": "SecurePass123",
        })
        assert resp.status_code == 201
        assert resp.json()["username"] == "myuser"

    async def test_special_chars_in_username_rejected(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.post("/auth/register", json={
            "username": "user name",
            "email": "u@example.com",
            "password": "SecurePass123",
        })
        assert resp.status_code == 422

    async def test_missing_fields_rejected(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.post("/auth/register", json={})
        assert resp.status_code == 422

    async def test_empty_body_rejected(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.post("/auth/register", content=b"")
        assert resp.status_code == 422


# ===========================================================================
# Login Tests
# ===========================================================================


class TestLogin:
    """POST /auth/login"""

    async def test_successful_login(self, auth_client: AsyncClient) -> None:
        await _register_user(auth_client)
        resp = await auth_client.post("/auth/login", json={
            "username": "testuser",
            "password": "SecurePass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    async def test_wrong_password_rejected(self, auth_client: AsyncClient) -> None:
        await _register_user(auth_client)
        resp = await auth_client.post("/auth/login", json={
            "username": "testuser",
            "password": "WrongPassword123",
        })
        assert resp.status_code == 401
        assert "Invalid username or password" in resp.json()["error"]["message"]

    async def test_nonexistent_user_rejected(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.post("/auth/login", json={
            "username": "ghost",
            "password": "SecurePass123",
        })
        assert resp.status_code == 401
        assert "Invalid username or password" in resp.json()["error"]["message"]

    async def test_inactive_user_rejected(self, auth_env: dict) -> None:
        client = auth_env["client"]
        db = auth_env["db"]

        await _register_user(client, "deactivated", "d@example.com")
        user = db.get_by_username("deactivated")
        user.is_active = False
        db.update_user(user)

        resp = await client.post("/auth/login", json={
            "username": "deactivated",
            "password": "SecurePass123",
        })
        assert resp.status_code == 403
        assert "deactivated" in resp.json()["error"]["message"].lower()

    async def test_login_returns_valid_access_token(self, auth_env: dict) -> None:
        """Access token from login should work on protected endpoints."""
        client = auth_env["client"]
        tokens = await _register_and_login(client)

        resp = await client.get("/auth/me", headers=_auth_header(tokens["access_token"]))
        assert resp.status_code == 200
        assert resp.json()["username"] == "testuser"

    async def test_error_message_doesnt_leak_which_field_failed(
        self, auth_client: AsyncClient,
    ) -> None:
        """Login error should not reveal whether username or password was wrong."""
        await _register_user(auth_client)

        # Wrong username
        r1 = await auth_client.post("/auth/login", json={
            "username": "wronguser",
            "password": "SecurePass123",
        })
        # Wrong password
        r2 = await auth_client.post("/auth/login", json={
            "username": "testuser",
            "password": "WrongPassword",
        })
        # Same generic message for both
        assert r1.json()["error"]["message"] == r2.json()["error"]["message"]


# ===========================================================================
# Token Refresh Tests
# ===========================================================================


class TestTokenRefresh:
    """POST /auth/refresh"""

    async def test_successful_refresh(self, auth_client: AsyncClient) -> None:
        tokens = await _register_and_login(auth_client)
        resp = await auth_client.post("/auth/refresh", json={
            "refresh_token": tokens["refresh_token"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    async def test_old_refresh_token_revoked_after_rotation(
        self, auth_client: AsyncClient,
    ) -> None:
        """After refresh, the old refresh token should be revoked."""
        tokens = await _register_and_login(auth_client)
        old_refresh = tokens["refresh_token"]

        # Use the refresh token
        resp = await auth_client.post("/auth/refresh", json={
            "refresh_token": old_refresh,
        })
        assert resp.status_code == 200

        # Try to reuse the old refresh token - should fail
        resp2 = await auth_client.post("/auth/refresh", json={
            "refresh_token": old_refresh,
        })
        assert resp2.status_code == 401
        assert "revoked" in resp2.json()["error"]["message"].lower()

    async def test_access_token_rejected_as_refresh(
        self, auth_client: AsyncClient,
    ) -> None:
        tokens = await _register_and_login(auth_client)
        resp = await auth_client.post("/auth/refresh", json={
            "refresh_token": tokens["access_token"],
        })
        assert resp.status_code == 401
        assert "Expected refresh token" in resp.json()["error"]["message"]

    async def test_invalid_refresh_token_rejected(
        self, auth_client: AsyncClient,
    ) -> None:
        resp = await auth_client.post("/auth/refresh", json={
            "refresh_token": "not.a.valid.jwt",
        })
        assert resp.status_code == 401

    async def test_refresh_returns_working_tokens(
        self, auth_client: AsyncClient,
    ) -> None:
        """New tokens from refresh should work on protected endpoints."""
        tokens = await _register_and_login(auth_client)
        resp = await auth_client.post("/auth/refresh", json={
            "refresh_token": tokens["refresh_token"],
        })
        new_tokens = resp.json()

        # Use new access token on /me
        me_resp = await auth_client.get(
            "/auth/me",
            headers=_auth_header(new_tokens["access_token"]),
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["username"] == "testuser"

    async def test_refresh_for_deactivated_user_rejected(self, auth_env: dict) -> None:
        client = auth_env["client"]
        db = auth_env["db"]

        tokens = await _register_and_login(client)

        # Deactivate the user after they got tokens
        user = db.get_by_username("testuser")
        user.is_active = False
        db.update_user(user)

        resp = await client.post("/auth/refresh", json={
            "refresh_token": tokens["refresh_token"],
        })
        assert resp.status_code == 401
        assert "deactivated" in resp.json()["error"]["message"].lower() or \
               "not found" in resp.json()["error"]["message"].lower()


# ===========================================================================
# Protected Endpoint Tests
# ===========================================================================


class TestProtectedEndpoints:
    """GET /auth/me and GET /auth/users"""

    async def test_me_with_valid_token(self, auth_client: AsyncClient) -> None:
        tokens = await _register_and_login(auth_client)
        resp = await auth_client.get(
            "/auth/me",
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"
        assert "hashed_password" not in data

    async def test_me_without_token_returns_401(self, auth_client: AsyncClient) -> None:
        resp = await auth_client.get("/auth/me")
        assert resp.status_code == 401

    async def test_me_with_invalid_token_returns_401(
        self, auth_client: AsyncClient,
    ) -> None:
        resp = await auth_client.get(
            "/auth/me",
            headers=_auth_header("totally.invalid.token"),
        )
        assert resp.status_code == 401

    async def test_me_with_tampered_token_returns_401(
        self, auth_client: AsyncClient,
    ) -> None:
        tokens = await _register_and_login(auth_client)
        tampered = tokens["access_token"][:-5] + "XXXXX"
        resp = await auth_client.get(
            "/auth/me",
            headers=_auth_header(tampered),
        )
        assert resp.status_code == 401

    async def test_me_with_refresh_token_rejected(
        self, auth_client: AsyncClient,
    ) -> None:
        """Using a refresh token where an access token is expected should fail."""
        tokens = await _register_and_login(auth_client)
        resp = await auth_client.get(
            "/auth/me",
            headers=_auth_header(tokens["refresh_token"]),
        )
        assert resp.status_code == 401
        assert "Expected access token" in resp.json()["error"]["message"]

    async def test_me_for_deleted_user_returns_401(self, auth_env: dict) -> None:
        client = auth_env["client"]
        db = auth_env["db"]

        tokens = await _register_and_login(client)

        # Delete the user from DB after login
        user = db.get_by_username("testuser")
        db.delete_user(user.id)

        resp = await client.get(
            "/auth/me",
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 401
        assert "not found" in resp.json()["error"]["message"].lower()

    async def test_me_for_deactivated_user_returns_403(self, auth_env: dict) -> None:
        client = auth_env["client"]
        db = auth_env["db"]

        tokens = await _register_and_login(client)

        user = db.get_by_username("testuser")
        user.is_active = False
        db.update_user(user)

        resp = await client.get(
            "/auth/me",
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 403
        assert "deactivated" in resp.json()["error"]["message"].lower()


# ===========================================================================
# Admin-Only Endpoint Tests
# ===========================================================================


class TestAdminEndpoints:
    """GET /auth/users (requires admin role)"""

    async def test_admin_can_list_users(self, auth_client: AsyncClient) -> None:
        # First user is auto-admin
        tokens = await _register_and_login(auth_client, "admin", "admin@ex.com")
        resp = await auth_client.get(
            "/auth/users",
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["username"] == "admin"

    async def test_viewer_cannot_list_users(self, auth_client: AsyncClient) -> None:
        # First user = admin, second = viewer
        await _register_user(auth_client, "admin", "admin@ex.com")
        tokens = await _register_and_login(auth_client, "viewer", "viewer@ex.com")

        resp = await auth_client.get(
            "/auth/users",
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 403
        assert "insufficient" in resp.json()["error"]["message"].lower()

    async def test_list_users_without_token_returns_401(
        self, auth_client: AsyncClient,
    ) -> None:
        resp = await auth_client.get("/auth/users")
        assert resp.status_code == 401

    async def test_admin_sees_all_users(self, auth_client: AsyncClient) -> None:
        admin_tokens = await _register_and_login(auth_client, "admin", "admin@ex.com")
        await _register_user(auth_client, "user2", "u2@ex.com")
        await _register_user(auth_client, "user3", "u3@ex.com")

        resp = await auth_client.get(
            "/auth/users",
            headers=_auth_header(admin_tokens["access_token"]),
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 3


# ===========================================================================
# Logout Tests
# ===========================================================================


class TestLogout:
    """POST /auth/logout"""

    async def test_successful_logout(self, auth_client: AsyncClient) -> None:
        tokens = await _register_and_login(auth_client)
        resp = await auth_client.post(
            "/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 200
        assert "logged out" in resp.json()["message"].lower()

    async def test_refresh_token_invalidated_after_logout(
        self, auth_client: AsyncClient,
    ) -> None:
        tokens = await _register_and_login(auth_client)
        # Logout
        await auth_client.post(
            "/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers=_auth_header(tokens["access_token"]),
        )
        # Try to refresh with the now-revoked token
        resp = await auth_client.post("/auth/refresh", json={
            "refresh_token": tokens["refresh_token"],
        })
        assert resp.status_code == 401
        assert "revoked" in resp.json()["error"]["message"].lower()

    async def test_logout_requires_access_token(
        self, auth_client: AsyncClient,
    ) -> None:
        tokens = await _register_and_login(auth_client)
        resp = await auth_client.post(
            "/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            # No Authorization header
        )
        assert resp.status_code == 401

    async def test_access_token_still_works_after_logout(
        self, auth_client: AsyncClient,
    ) -> None:
        """Access tokens aren't revoked on logout - they expire naturally."""
        tokens = await _register_and_login(auth_client)
        await auth_client.post(
            "/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers=_auth_header(tokens["access_token"]),
        )
        # Access token should still be valid (not blacklisted)
        resp = await auth_client.get(
            "/auth/me",
            headers=_auth_header(tokens["access_token"]),
        )
        assert resp.status_code == 200


# ===========================================================================
# Token Expiration Tests
# ===========================================================================


class TestTokenExpiration:
    """Edge cases around token lifetimes."""

    async def test_expired_access_token_rejected(self) -> None:
        """An immediately-expiring token should fail after a brief wait."""
        app, config, db, token_service = _create_test_app(
            access_token_expire_minutes=0,
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _register_user(client)
            tokens = await _login_user(client)
            time.sleep(0.2)

            resp = await client.get(
                "/auth/me",
                headers=_auth_header(tokens["access_token"]),
            )
            assert resp.status_code == 401
            assert "expired" in resp.json()["error"]["message"].lower()

    async def test_expired_refresh_token_rejected(self) -> None:
        """An immediately-expiring refresh token should fail."""
        app, config, db, token_service = _create_test_app(
            refresh_token_expire_days=0,
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _register_user(client)
            tokens = await _login_user(client)
            time.sleep(0.2)

            resp = await client.post("/auth/refresh", json={
                "refresh_token": tokens["refresh_token"],
            })
            assert resp.status_code == 401
            assert "expired" in resp.json()["error"]["message"].lower()


# ===========================================================================
# Full Auth Lifecycle Tests
# ===========================================================================


class TestFullAuthLifecycle:
    """End-to-end auth flows combining multiple operations."""

    async def test_register_login_access_refresh_logout(
        self, auth_client: AsyncClient,
    ) -> None:
        """Complete lifecycle: register -> login -> use -> refresh -> logout."""
        # 1. Register
        reg_resp = await auth_client.post("/auth/register", json={
            "username": "lifecycle",
            "email": "life@example.com",
            "password": "SecurePass123",
        })
        assert reg_resp.status_code == 201

        # 2. Login
        login_resp = await auth_client.post("/auth/login", json={
            "username": "lifecycle",
            "password": "SecurePass123",
        })
        assert login_resp.status_code == 200
        tokens = login_resp.json()

        # 3. Access protected resource
        me_resp = await auth_client.get(
            "/auth/me",
            headers=_auth_header(tokens["access_token"]),
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["username"] == "lifecycle"

        # 4. Refresh tokens
        refresh_resp = await auth_client.post("/auth/refresh", json={
            "refresh_token": tokens["refresh_token"],
        })
        assert refresh_resp.status_code == 200
        new_tokens = refresh_resp.json()

        # 5. Old refresh token no longer works
        old_refresh_resp = await auth_client.post("/auth/refresh", json={
            "refresh_token": tokens["refresh_token"],
        })
        assert old_refresh_resp.status_code == 401

        # 6. New tokens work
        me_resp2 = await auth_client.get(
            "/auth/me",
            headers=_auth_header(new_tokens["access_token"]),
        )
        assert me_resp2.status_code == 200

        # 7. Logout
        logout_resp = await auth_client.post(
            "/auth/logout",
            json={"refresh_token": new_tokens["refresh_token"]},
            headers=_auth_header(new_tokens["access_token"]),
        )
        assert logout_resp.status_code == 200

        # 8. Refresh token is now revoked
        final_refresh = await auth_client.post("/auth/refresh", json={
            "refresh_token": new_tokens["refresh_token"],
        })
        assert final_refresh.status_code == 401

    async def test_multiple_users_isolated(self, auth_client: AsyncClient) -> None:
        """Tokens from one user should not access another's data."""
        tokens_a = await _register_and_login(auth_client, "alice", "alice@ex.com")
        tokens_b = await _register_and_login(auth_client, "bob", "bob@ex.com")

        # Alice's token returns Alice
        resp_a = await auth_client.get(
            "/auth/me",
            headers=_auth_header(tokens_a["access_token"]),
        )
        assert resp_a.json()["username"] == "alice"

        # Bob's token returns Bob
        resp_b = await auth_client.get(
            "/auth/me",
            headers=_auth_header(tokens_b["access_token"]),
        )
        assert resp_b.json()["username"] == "bob"

    async def test_login_after_logout_gives_new_tokens(
        self, auth_client: AsyncClient,
    ) -> None:
        """Users can log in again after logging out."""
        tokens1 = await _register_and_login(auth_client)

        # Logout
        await auth_client.post(
            "/auth/logout",
            json={"refresh_token": tokens1["refresh_token"]},
            headers=_auth_header(tokens1["access_token"]),
        )

        # Login again - should succeed and return valid tokens
        tokens2 = await _login_user(auth_client)
        assert "access_token" in tokens2
        assert "refresh_token" in tokens2

        # New tokens work
        resp = await auth_client.get(
            "/auth/me",
            headers=_auth_header(tokens2["access_token"]),
        )
        assert resp.status_code == 200
