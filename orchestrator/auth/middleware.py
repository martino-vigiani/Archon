"""FastAPI auth middleware - dependency injection for route protection."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import UserDatabase
from .models import APIError, Role, User
from .tokens import TokenError, TokenService

# Shared instances - initialized by create_auth_router()
_token_service: TokenService | None = None
_user_db: UserDatabase | None = None

security_scheme = HTTPBearer(auto_error=False)


def init_middleware(token_service: TokenService, user_db: UserDatabase) -> None:
    """Initialize middleware with shared service instances.

    Called by create_auth_router() during setup.
    """
    global _token_service, _user_db
    _token_service = token_service
    _user_db = user_db


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> User:
    """FastAPI dependency that extracts and validates the current user from the JWT.

    Usage:
        @app.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"user": user.username}

    Raises:
        HTTPException 401: If token is missing, invalid, or expired.
        HTTPException 403: If user account is deactivated.
    """
    if _token_service is None or _user_db is None:
        raise APIError(
            status_code=500,
            code="INTERNAL_ERROR",
            message="Auth system not initialized",
        )

    if credentials is None:
        raise APIError(
            status_code=401,
            code="UNAUTHORIZED",
            message="Authentication required",
        )

    try:
        payload = _token_service.decode_token(credentials.credentials, expected_type="access")
    except TokenError as e:
        raise APIError(
            status_code=401,
            code="UNAUTHORIZED",
            message=str(e),
        )

    user = _user_db.get_by_id(payload["sub"])
    if user is None:
        raise APIError(
            status_code=401,
            code="UNAUTHORIZED",
            message="User not found",
        )

    if not user.is_active:
        raise APIError(
            status_code=403,
            code="FORBIDDEN",
            message="Account is deactivated",
        )

    return user


def require_role(required_role: Role) -> Callable[..., User]:
    """Create a dependency that requires a specific role level.

    Usage:
        @app.delete("/admin-only")
        async def admin_route(user: User = Depends(require_role(Role.ADMIN))):
            return {"message": "admin access granted"}

    Args:
        required_role: Minimum role required to access the endpoint.

    Returns:
        A FastAPI dependency function.
    """

    async def role_checker(
        user: User = Depends(get_current_user),
    ) -> User:
        if not Role.has_permission(user.role, required_role):
            raise APIError(
                status_code=403,
                code="FORBIDDEN",
                message=f"Role '{user.role.value}' insufficient. Requires '{required_role.value}' or higher.",
            )
        return user

    return role_checker
