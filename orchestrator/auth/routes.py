"""Auth API endpoints - register, login, refresh, logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from .config import AuthConfig
from .database import UserDatabase
from .middleware import get_current_user, init_middleware, require_role
from .models import (
    APIError,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    Role,
    TokenResponse,
    User,
    UserCreate,
    UserResponse,
)
from .passwords import PasswordHasher
from .tokens import TokenError, TokenService


def create_auth_router(
    config: AuthConfig | None = None,
    db: UserDatabase | None = None,
    token_service: TokenService | None = None,
) -> APIRouter:
    """Create and configure the auth API router.

    Args:
        config: Auth configuration. Uses defaults if None.
        db: User database. Creates in-memory DB if None.
        token_service: Token service. Creates default if None.

    Returns:
        Configured FastAPI APIRouter with auth endpoints.
    """
    config = config or AuthConfig()
    db = db or UserDatabase(config.db_path)
    token_service = token_service or TokenService(config)
    hasher = PasswordHasher()

    # Initialize shared middleware instances
    init_middleware(token_service, db)

    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post(
        "/register",
        response_model=UserResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def register(data: UserCreate) -> UserResponse:
        """Register a new user account.

        Creates a user with hashed password and default viewer role.
        The first registered user is automatically promoted to admin.
        """
        # Check password strength
        if len(data.password) < config.min_password_length:
            raise APIError(
                status_code=400,
                code="VALIDATION_ERROR",
                message=f"Password must be at least {config.min_password_length} characters",
            )

        # First user gets admin role
        role = data.role
        if db.count_users() == 0:
            role = Role.ADMIN

        user = User(
            username=data.username,
            email=data.email,
            hashed_password=hasher.hash(data.password),
            role=role,
        )

        try:
            db.create_user(user)
        except ValueError as e:
            raise APIError(
                status_code=409,
                code="CONFLICT",
                message=str(e),
            )

        return UserResponse(**user.to_dict())

    @router.post("/login", response_model=TokenResponse)
    async def login(data: LoginRequest) -> TokenResponse:
        """Authenticate and receive access + refresh tokens.

        Validates username and password, returns JWT token pair.
        """
        user = db.get_by_username(data.username)
        if user is None or not hasher.verify(data.password, user.hashed_password):
            raise APIError(
                status_code=401,
                code="INVALID_CREDENTIALS",
                message="Invalid username or password",
            )

        if not user.is_active:
            raise APIError(
                status_code=403,
                code="FORBIDDEN",
                message="Account is deactivated",
            )

        tokens = token_service.create_token_pair(user.id, user.role.value)
        return TokenResponse(**tokens)

    @router.post("/refresh", response_model=TokenResponse)
    async def refresh(data: RefreshRequest) -> TokenResponse:
        """Exchange a valid refresh token for a new token pair.

        The old refresh token is revoked after use (rotation).
        """
        try:
            payload = token_service.decode_token(data.refresh_token, expected_type="refresh")
        except TokenError as e:
            raise APIError(
                status_code=401,
                code="INVALID_TOKEN",
                message=str(e),
            )

        user = db.get_by_id(payload["sub"])
        if user is None or not user.is_active:
            raise APIError(
                status_code=401,
                code="INVALID_TOKEN",
                message="User not found or deactivated",
            )

        # Revoke old refresh token (rotation)
        token_service.revoke_refresh_token(data.refresh_token)

        # Issue new pair
        tokens = token_service.create_token_pair(user.id, user.role.value)
        return TokenResponse(**tokens)

    @router.post("/logout", response_model=MessageResponse)
    async def logout(
        data: RefreshRequest,
        _user: User = Depends(get_current_user),
    ) -> MessageResponse:
        """Revoke the refresh token, effectively logging out.

        Requires a valid access token in the Authorization header
        and the refresh token in the request body.
        """
        token_service.revoke_refresh_token(data.refresh_token)
        return MessageResponse(message="Logged out successfully")

    @router.get("/me", response_model=UserResponse)
    async def me(user: User = Depends(get_current_user)) -> UserResponse:
        """Get the current authenticated user's profile."""
        return UserResponse(**user.to_dict())

    @router.get("/users", response_model=list[UserResponse])
    async def list_users(
        _admin: User = Depends(require_role(Role.ADMIN)),
    ) -> list[UserResponse]:
        """List all users. Admin only."""
        users = db.list_users(active_only=False)
        return [UserResponse(**u.to_dict()) for u in users]

    return router
