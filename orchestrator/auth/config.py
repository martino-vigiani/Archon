"""Auth configuration - secrets, expiration times, and database path."""

import os
import secrets
import warnings
from dataclasses import dataclass, field
from pathlib import Path

# Minimum acceptable length for an HS256 signing secret (chars). A short secret
# is brute-forceable offline from any captured JWT, after which tokens can be
# forged (role=admin, arbitrary sub).
_MIN_SECRET_LEN = 32


def _resolve_secret_key() -> str:
    """Resolve the JWT signing secret, warning on weak or ephemeral keys.

    * If ``ARCHON_SECRET_KEY`` is set, use it — but warn if it is too short to
      resist offline brute-force.
    * If it is unset, generate a strong per-process key and warn that it is
      ephemeral: tokens become invalid on restart and are NOT shared across the
      dashboard / live-API processes. Set ``ARCHON_SECRET_KEY`` for a stable,
      shared secret in any real deployment.
    """
    env_key = os.environ.get("ARCHON_SECRET_KEY")
    if env_key:
        if len(env_key) < _MIN_SECRET_LEN:
            warnings.warn(
                f"ARCHON_SECRET_KEY is shorter than {_MIN_SECRET_LEN} chars; "
                "use a long, high-entropy secret to prevent JWT forgery.",
                stacklevel=2,
            )
        return env_key
    warnings.warn(
        "ARCHON_SECRET_KEY is not set; using an ephemeral per-process secret. "
        "Tokens will not survive a restart and are not shared across processes. "
        "Set ARCHON_SECRET_KEY for a stable, shared signing secret.",
        stacklevel=2,
    )
    return secrets.token_hex(32)


@dataclass
class AuthConfig:
    """Configuration for authentication system."""

    # JWT settings
    secret_key: str = field(default_factory=_resolve_secret_key)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Database
    db_path: Path = field(
        default_factory=lambda: Path(__file__).parent.parent.parent / ".orchestra" / "auth.db"
    )

    # Password policy
    min_password_length: int = 8

    # Token issuer
    issuer: str = "archon"
