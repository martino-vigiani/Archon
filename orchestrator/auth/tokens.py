"""JWT token service - access and refresh token management."""

from __future__ import annotations

import contextlib
import json
import os
import stat
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt

from .config import AuthConfig


class TokenError(Exception):
    """Raised when token operations fail."""


class _RevocationStore:
    """Thread-safe revocation state, optionally persisted to a JSON file.

    Tracks two things:

    * ``jtis`` — individually revoked token ids (used for refresh-token rotation).
    * ``user_cutoff`` — a per-user epoch-seconds cutoff; any token whose ``iat``
      predates the cutoff is considered revoked. Setting the cutoff to "now"
      revokes ALL of a user's outstanding tokens (used by logout).

    With a ``path`` the state is loaded on init and rewritten on every mutation,
    so revocation survives a restart and is shared across processes on the same
    host (each reads the file). Without a ``path`` it is purely in-memory
    (the historical behavior).
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self.jtis: set[str] = set()
        self.user_cutoff: dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        with contextlib.suppress(OSError, ValueError, TypeError):
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.jtis = set(data.get("jtis", []))
            self.user_cutoff = {str(k): float(v) for k, v in data.get("user_cutoff", {}).items()}

    def _save(self) -> None:
        if not self.path:
            return
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"jtis": sorted(self.jtis), "user_cutoff": self.user_cutoff}),
                encoding="utf-8",
            )
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

    def revoke_jti(self, jti: str) -> None:
        with self._lock:
            self.jtis.add(jti)
            self._save()

    def revoke_user(self, user_id: str, cutoff_epoch: float) -> None:
        with self._lock:
            # Keep the latest cutoff if logout is called repeatedly.
            self.user_cutoff[user_id] = max(cutoff_epoch, self.user_cutoff.get(user_id, 0.0))
            self._save()

    def is_jti_revoked(self, jti: str) -> bool:
        with self._lock:
            if self.path:
                self._load()
            return jti in self.jtis

    def is_user_token_revoked(self, user_id: str, issued_at_epoch: float) -> bool:
        with self._lock:
            if self.path:
                self._load()
            cutoff = self.user_cutoff.get(user_id)
            return cutoff is not None and issued_at_epoch < cutoff


class TokenService:
    """Manages JWT access and refresh tokens."""

    def __init__(
        self,
        config: AuthConfig | None = None,
        revocation_path: Path | str | None = None,
    ) -> None:
        self.config = config or AuthConfig()
        # Revocation state. A ``revocation_path`` makes it persistent + shared
        # across processes; the default is in-memory (per-process).
        self._revocation = _RevocationStore(revocation_path)

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
            "jti": uuid.uuid4().hex,
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
            "jti": uuid.uuid4().hex,
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

        # Per-user revocation (logout-all revokes every token issued before the cutoff).
        sub = payload.get("sub")
        iat = payload.get("iat")
        if sub and isinstance(iat, (int, float)) and self._revocation.is_user_token_revoked(sub, float(iat)):
            raise TokenError("Token has been revoked")

        # Per-token revocation by jti (refresh-token rotation, single-session
        # logout). Applies to both access and refresh tokens.
        jti = payload.get("jti")
        if (jti and self._revocation.is_jti_revoked(jti)) or token in self._revocation.jtis:
            raise TokenError("Token has been revoked")

        return payload

    def _jti_of(self, token: str) -> str:
        """Best-effort extract a token's ``jti`` without verifying its signature.

        Revocation is harmless to perform on an unverified token (you can only
        revoke a token you hold), so this tolerates expired/odd tokens. Falls
        back to the raw token string when no ``jti`` claim is present.
        """
        with contextlib.suppress(jwt.InvalidTokenError, ValueError, TypeError):
            unverified = jwt.decode(token, options={"verify_signature": False})
            jti = unverified.get("jti")
            if jti:
                return str(jti)
        return token

    def revoke_token(self, token: str) -> None:
        """Revoke a single token (access or refresh) by its jti.

        Used for single-session logout (revoke the presented access token) and
        refresh-token rotation. Idempotent.
        """
        self._revocation.revoke_jti(self._jti_of(token))

    def revoke_refresh_token(self, token: str) -> None:
        """Add a refresh token to the blacklist (by jti).

        Args:
            token: The refresh token to revoke.
        """
        self.revoke_token(token)

    def revoke_user(self, user_id: str) -> None:
        """Revoke every outstanding token for a user (logout-all).

        Sets a per-user cutoff to the current time so any token issued earlier is
        rejected by :meth:`decode_token`.
        """
        now_epoch = datetime.now(timezone.utc).timestamp()
        self._revocation.revoke_user(user_id, now_epoch)

    def is_revoked(self, token: str) -> bool:
        """Check if a refresh token has been revoked.

        Args:
            token: The refresh token to check.

        Returns:
            True if the token has been revoked.
        """
        return self._revocation.is_jti_revoked(self._jti_of(token))
