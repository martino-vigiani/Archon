"""
Archon Auth Module - JWT authentication with role-based access control.

Provides user registration, login, token management, and route protection
for the Archon dashboard API.
"""

from .config import AuthConfig
from .database import UserDatabase
from .error_handlers import register_error_handlers
from .middleware import get_current_user, require_role
from .models import APIError, ErrorResponse, Role, User, UserCreate, UserResponse
from .passwords import PasswordHasher
from .routes import create_auth_router
from .tokens import TokenService

__all__ = [
    "APIError",
    "AuthConfig",
    "create_auth_router",
    "ErrorResponse",
    "get_current_user",
    "PasswordHasher",
    "register_error_handlers",
    "require_role",
    "Role",
    "TokenService",
    "User",
    "UserCreate",
    "UserDatabase",
    "UserResponse",
]
