"""Password hashing with bcrypt.

bcrypt silently truncates the input to 72 bytes, so two long passwords that
share their first 72 bytes would hash equal. To preserve the full password's
entropy (and accept passwords longer than 72 bytes safely) we pre-hash the
password with SHA-256 and bcrypt the hex digest (64 ASCII chars, always < 72
bytes). ``verify`` also falls back to the legacy direct-bcrypt path so hashes
created before this change still validate.
"""

import hashlib

import bcrypt


def _prehash(password: str) -> bytes:
    """Return the SHA-256 hex digest of the password as bytes for bcrypt.

    The digest is 64 ASCII characters, so bcrypt's 72-byte limit never truncates
    meaningful entropy regardless of the original password length.
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


class PasswordHasher:
    """Handles password hashing and verification using bcrypt."""

    @staticmethod
    def hash(password: str) -> str:
        """Hash a plaintext password.

        Args:
            password: The plaintext password to hash.

        Returns:
            The bcrypt-hashed password string (over the SHA-256 pre-hash).
        """
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(_prehash(password), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify(password: str, hashed: str) -> bool:
        """Verify a plaintext password against a bcrypt hash.

        Tries the SHA-256 pre-hash scheme first, then falls back to the legacy
        direct-bcrypt scheme so hashes created before the pre-hash change still
        validate. Returns False on any malformed-hash error rather than raising.

        Args:
            password: The plaintext password to check.
            hashed: The bcrypt hash to check against.

        Returns:
            True if the password matches the hash.
        """
        hashed_bytes = hashed.encode("utf-8")
        try:
            if bcrypt.checkpw(_prehash(password), hashed_bytes):
                return True
        except (ValueError, TypeError):
            return False
        # Legacy fallback: hashes minted before the SHA-256 pre-hash was added.
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed_bytes)
        except (ValueError, TypeError):
            return False
