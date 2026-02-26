"""Auth configuration - secrets, expiration times, and database path."""

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AuthConfig:
    """Configuration for authentication system."""

    # JWT settings
    secret_key: str = field(
        default_factory=lambda: os.environ.get("ARCHON_SECRET_KEY", secrets.token_hex(32))
    )
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
