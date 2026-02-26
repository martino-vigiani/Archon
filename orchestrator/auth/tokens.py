"""JWT token service - access and refresh token management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from .config import AuthConfig


class TokenError(Exception):
    """Raised when token operations fail."""


class TokenService:
    """Manages JWT access and refresh tokens."""

    def __init__(self, config: AuthConfig | None = None) -> None:
        self.config = config or AuthConfig()
        # In-memory blacklist for revoked refresh tokens.
        # For a local dev tool this is sufficient; production would use Redis.
        self._revoked_tokens: set[str] = set()

    def create_access_token(self, user_id: str, role: str) -> str:
        """Create a short-lived access token.

        Args:
            user_id: The user's unique identifier.
            role: The user's role string.

        Returns:
            Encoded JWT access token.
        """
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "role": role,
            "type": "access",
            "iss": self.config.issuer,
            "iat": now,
            "exp": now + timedelta(minutes=self.config.access_token_expire_minutes),
        }
        return jwt.encode(payload, self.config.secret_key, algorithm=self.config.algorithm)

    def create_refresh_token(self, user_id: str) -> str:
        """Create a long-lived refresh token.

        Args:
            user_id: The user's unique identifier.

        Returns:
            Encoded JWT refresh token.
        """
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "type": "refresh",
            "iss": self.config.issuer,
            "iat": now,
            "exp": now + timedelta(days=self.config.refresh_token_expire_days),
        }
        return jwt.encode(payload, self.config.secret_key, algorithm=self.config.algorithm)

    def create_token_pair(self, user_id: str, role: str) -> dict[str, Any]:
        """Create both access and refresh tokens.

        Args:
            user_id: The user's unique identifier.
            role: The user's role string.

        Returns:
            Dictionary with access_token, refresh_token, token_type, and expires_in.
        """
        return {
            "access_token": self.create_access_token(user_id, role),
            "refresh_token": self.create_refresh_token(user_id),
            "token_type": "bearer",
            "expires_in": self.config.access_token_expire_minutes * 60,
        }

    def decode_token(self, token: str, expected_type: str = "access") -> dict[str, Any]:
        """Decode and validate a JWT token.

        Args:
            token: The encoded JWT string.
            expected_type: Expected token type ("access" or "refresh").

        Returns:
            The decoded token payload.

        Raises:
            TokenError: If the token is invalid, expired, or revoked.
        """
        try:
            payload = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
                issuer=self.config.issuer,
            )
        except jwt.ExpiredSignatureError:
            raise TokenError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise TokenError(f"Invalid token: {e}")

        if payload.get("type") != expected_type:
            raise TokenError(f"Expected {expected_type} token, got {payload.get('type')}")

        if expected_type == "refresh" and token in self._revoked_tokens:
            raise TokenError("Token has been revoked")

        return payload

    def revoke_refresh_token(self, token: str) -> None:
        """Add a refresh token to the blacklist.

        Args:
            token: The refresh token to revoke.
        """
        self._revoked_tokens.add(token)

    def is_revoked(self, token: str) -> bool:
        """Check if a refresh token has been revoked.

        Args:
            token: The refresh token to check.

        Returns:
            True if the token has been revoked.
        """
        return token in self._revoked_tokens
