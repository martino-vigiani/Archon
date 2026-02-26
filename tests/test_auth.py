"""Tests for the auth module - passwords, tokens, database, RBAC, and routes."""

import time

import pytest

from orchestrator.auth.config import AuthConfig
from orchestrator.auth.database import UserDatabase
from orchestrator.auth.models import Role, User, UserCreate
from orchestrator.auth.passwords import PasswordHasher
from orchestrator.auth.tokens import TokenError, TokenService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_config():
    """Auth config with short expiration for fast tests."""
    return AuthConfig(
        secret_key="test-secret-key-for-unit-tests-min32b",
        access_token_expire_minutes=1,
        refresh_token_expire_days=1,
        db_path=":memory:",
        min_password_length=8,
    )


@pytest.fixture
def hasher():
    return PasswordHasher()


@pytest.fixture
def token_service(auth_config):
    return TokenService(auth_config)


@pytest.fixture
def db():
    """In-memory database for each test."""
    return UserDatabase(":memory:")


@pytest.fixture
def sample_user(hasher):
    """A pre-built user with known password."""
    return User(
        username="testuser",
        email="test@example.com",
        hashed_password=hasher.hash("SecurePass123"),
        role=Role.VIEWER,
    )


# ---------------------------------------------------------------------------
# Password Hashing Tests
# ---------------------------------------------------------------------------


class TestPasswordHasher:
    def test_hash_returns_bcrypt_string(self, hasher):
        hashed = hasher.hash("mypassword")
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

    def test_verify_correct_password(self, hasher):
        hashed = hasher.hash("correctpassword")
        assert hasher.verify("correctpassword", hashed) is True

    def test_verify_wrong_password(self, hasher):
        hashed = hasher.hash("correctpassword")
        assert hasher.verify("wrongpassword", hashed) is False

    def test_hash_is_unique_per_call(self, hasher):
        h1 = hasher.hash("same_password")
        h2 = hasher.hash("same_password")
        assert h1 != h2  # Different salts

    def test_empty_password_still_hashes(self, hasher):
        hashed = hasher.hash("")
        assert hasher.verify("", hashed) is True

    def test_unicode_password(self, hasher):
        pwd = "p\u00e4ssw\u00f6rd\U0001f512"
        hashed = hasher.hash(pwd)
        assert hasher.verify(pwd, hashed) is True


# ---------------------------------------------------------------------------
# Token Service Tests
# ---------------------------------------------------------------------------


class TestTokenService:
    def test_create_access_token(self, token_service):
        token = token_service.create_access_token("user123", "admin")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_create_refresh_token(self, token_service):
        token = token_service.create_refresh_token("user123")
        assert isinstance(token, str)

    def test_decode_access_token(self, token_service):
        token = token_service.create_access_token("user123", "admin")
        payload = token_service.decode_token(token, expected_type="access")
        assert payload["sub"] == "user123"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_decode_refresh_token(self, token_service):
        token = token_service.create_refresh_token("user456")
        payload = token_service.decode_token(token, expected_type="refresh")
        assert payload["sub"] == "user456"
        assert payload["type"] == "refresh"

    def test_wrong_token_type_rejected(self, token_service):
        access = token_service.create_access_token("user1", "viewer")
        with pytest.raises(TokenError, match="Expected refresh token"):
            token_service.decode_token(access, expected_type="refresh")

    def test_tampered_token_rejected(self, token_service):
        token = token_service.create_access_token("user1", "viewer")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(TokenError, match="Invalid token"):
            token_service.decode_token(tampered)

    def test_expired_token_rejected(self):
        config = AuthConfig(
            secret_key="test-key-for-expiry-check-min32bytes",
            access_token_expire_minutes=0,  # Immediate expiration
        )
        svc = TokenService(config)
        token = svc.create_access_token("user1", "viewer")
        # Token is already expired (0 minutes)
        time.sleep(0.1)
        with pytest.raises(TokenError, match="expired"):
            svc.decode_token(token)

    def test_create_token_pair(self, token_service):
        pair = token_service.create_token_pair("user1", "admin")
        assert "access_token" in pair
        assert "refresh_token" in pair
        assert pair["token_type"] == "bearer"
        assert pair["expires_in"] == 60  # 1 minute * 60 seconds

    def test_revoke_refresh_token(self, token_service):
        token = token_service.create_refresh_token("user1")
        assert token_service.is_revoked(token) is False

        token_service.revoke_refresh_token(token)
        assert token_service.is_revoked(token) is True

        with pytest.raises(TokenError, match="revoked"):
            token_service.decode_token(token, expected_type="refresh")

    def test_different_secret_rejects_token(self):
        svc1 = TokenService(AuthConfig(secret_key="secret-one-that-is-at-least-32bytes"))
        svc2 = TokenService(AuthConfig(secret_key="secret-two-that-is-at-least-32bytes"))
        token = svc1.create_access_token("user1", "viewer")
        with pytest.raises(TokenError, match="Invalid token"):
            svc2.decode_token(token)


# ---------------------------------------------------------------------------
# User Database Tests
# ---------------------------------------------------------------------------


class TestUserDatabase:
    def test_create_and_retrieve_user(self, db, sample_user):
        db.create_user(sample_user)
        found = db.get_by_username("testuser")
        assert found is not None
        assert found.username == "testuser"
        assert found.email == "test@example.com"
        assert found.role == Role.VIEWER

    def test_get_by_id(self, db, sample_user):
        db.create_user(sample_user)
        found = db.get_by_id(sample_user.id)
        assert found is not None
        assert found.id == sample_user.id

    def test_get_by_email(self, db, sample_user):
        db.create_user(sample_user)
        found = db.get_by_email("test@example.com")
        assert found is not None
        assert found.email == "test@example.com"

    def test_user_not_found_returns_none(self, db):
        assert db.get_by_username("nonexistent") is None
        assert db.get_by_id("nonexistent") is None
        assert db.get_by_email("no@where.com") is None

    def test_duplicate_username_raises(self, db, sample_user):
        db.create_user(sample_user)
        dupe = User(
            username="testuser",
            email="other@example.com",
            hashed_password="hashed",
            role=Role.VIEWER,
        )
        with pytest.raises(ValueError, match="already exists"):
            db.create_user(dupe)

    def test_duplicate_email_raises(self, db, sample_user):
        db.create_user(sample_user)
        dupe = User(
            username="otheruser",
            email="test@example.com",
            hashed_password="hashed",
            role=Role.VIEWER,
        )
        with pytest.raises(ValueError, match="already exists"):
            db.create_user(dupe)

    def test_update_user(self, db, sample_user):
        db.create_user(sample_user)
        sample_user.role = Role.ADMIN
        assert db.update_user(sample_user) is True

        updated = db.get_by_id(sample_user.id)
        assert updated is not None
        assert updated.role == Role.ADMIN

    def test_update_nonexistent_user(self, db):
        ghost = User(id="nonexistent", username="ghost", email="g@g.com", hashed_password="x")
        assert db.update_user(ghost) is False

    def test_delete_user(self, db, sample_user):
        db.create_user(sample_user)
        assert db.delete_user(sample_user.id) is True
        assert db.get_by_id(sample_user.id) is None

    def test_delete_nonexistent_user(self, db):
        assert db.delete_user("nonexistent") is False

    def test_list_users(self, db, hasher):
        for i in range(3):
            db.create_user(User(
                username=f"user{i}",
                email=f"user{i}@test.com",
                hashed_password=hasher.hash("password"),
            ))
        users = db.list_users()
        assert len(users) == 3

    def test_list_active_only(self, db, hasher):
        active = User(username="active", email="a@t.com", hashed_password="h", is_active=True)
        inactive = User(username="inactive", email="i@t.com", hashed_password="h", is_active=False)
        db.create_user(active)
        db.create_user(inactive)

        assert len(db.list_users(active_only=True)) == 1
        assert len(db.list_users(active_only=False)) == 2

    def test_count_users(self, db, sample_user):
        assert db.count_users() == 0
        db.create_user(sample_user)
        assert db.count_users() == 1


# ---------------------------------------------------------------------------
# Role / RBAC Tests
# ---------------------------------------------------------------------------


class TestRBAC:
    def test_admin_has_all_permissions(self):
        assert Role.has_permission(Role.ADMIN, Role.ADMIN) is True
        assert Role.has_permission(Role.ADMIN, Role.OPERATOR) is True
        assert Role.has_permission(Role.ADMIN, Role.VIEWER) is True

    def test_operator_permissions(self):
        assert Role.has_permission(Role.OPERATOR, Role.ADMIN) is False
        assert Role.has_permission(Role.OPERATOR, Role.OPERATOR) is True
        assert Role.has_permission(Role.OPERATOR, Role.VIEWER) is True

    def test_viewer_permissions(self):
        assert Role.has_permission(Role.VIEWER, Role.ADMIN) is False
        assert Role.has_permission(Role.VIEWER, Role.OPERATOR) is False
        assert Role.has_permission(Role.VIEWER, Role.VIEWER) is True


# ---------------------------------------------------------------------------
# Pydantic Model Validation Tests
# ---------------------------------------------------------------------------


class TestUserCreate:
    def test_valid_user(self):
        u = UserCreate(username="john", email="john@test.com", password="SecurePass1")
        assert u.username == "john"

    def test_username_lowered(self):
        u = UserCreate(username="JOHN", email="j@test.com", password="SecurePass1")
        assert u.username == "john"

    def test_short_username_rejected(self):
        with pytest.raises(Exception):
            UserCreate(username="ab", email="a@t.com", password="SecurePass1")

    def test_invalid_username_chars(self):
        with pytest.raises(Exception):
            UserCreate(username="user name", email="a@t.com", password="SecurePass1")

    def test_invalid_email(self):
        with pytest.raises(Exception):
            UserCreate(username="user", email="not-an-email", password="SecurePass1")

    def test_short_password_rejected(self):
        with pytest.raises(Exception):
            UserCreate(username="user", email="u@t.com", password="short")

    def test_dashes_and_underscores_allowed(self):
        u = UserCreate(username="my-user_01", email="u@t.com", password="SecurePass1")
        assert u.username == "my-user_01"


# ---------------------------------------------------------------------------
# User Model Tests
# ---------------------------------------------------------------------------


class TestUserModel:
    def test_to_dict_excludes_password(self, sample_user):
        d = sample_user.to_dict()
        assert "hashed_password" not in d
        assert "username" in d
        assert "role" in d

    def test_from_row_roundtrip(self, sample_user):
        row = (
            sample_user.id,
            sample_user.username,
            sample_user.email,
            sample_user.hashed_password,
            sample_user.role.value,
            int(sample_user.is_active),
            sample_user.created_at,
            sample_user.updated_at,
        )
        restored = User.from_row(row)
        assert restored.id == sample_user.id
        assert restored.username == sample_user.username
        assert restored.role == sample_user.role


# ---------------------------------------------------------------------------
# Integration: Auth Flow Tests
# ---------------------------------------------------------------------------


class TestAuthFlow:
    """End-to-end auth flow without HTTP (direct function calls)."""

    def test_register_login_flow(self, db, hasher, token_service):
        # Register
        hashed = hasher.hash("MyPassword123")
        user = User(username="flowuser", email="flow@test.com", hashed_password=hashed)
        db.create_user(user)

        # Login - verify password
        found = db.get_by_username("flowuser")
        assert found is not None
        assert hasher.verify("MyPassword123", found.hashed_password)

        # Get tokens
        pair = token_service.create_token_pair(found.id, found.role.value)
        payload = token_service.decode_token(pair["access_token"])
        assert payload["sub"] == found.id
        assert payload["role"] == "viewer"

    def test_refresh_and_revoke_flow(self, db, hasher, token_service):
        hashed = hasher.hash("Password123")
        user = User(username="refreshuser", email="r@test.com", hashed_password=hashed)
        db.create_user(user)

        # Create initial tokens
        pair = token_service.create_token_pair(user.id, user.role.value)
        refresh = pair["refresh_token"]

        # Refresh token should be valid
        payload = token_service.decode_token(refresh, expected_type="refresh")
        assert payload["sub"] == user.id

        # Revoke (logout)
        token_service.revoke_refresh_token(refresh)

        # Revoked token should fail
        with pytest.raises(TokenError, match="revoked"):
            token_service.decode_token(refresh, expected_type="refresh")

    def test_first_user_gets_admin_check(self, db):
        """Verify the DB starts empty (first user logic is in routes)."""
        assert db.count_users() == 0

    def test_inactive_user_cannot_be_found_active(self, db, hasher):
        user = User(
            username="inactive",
            email="in@test.com",
            hashed_password=hasher.hash("pass1234"),
            is_active=False,
        )
        db.create_user(user)
        active_users = db.list_users(active_only=True)
        assert len(active_users) == 0
