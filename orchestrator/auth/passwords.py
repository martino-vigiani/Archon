"""Password hashing with bcrypt."""

import bcrypt


class PasswordHasher:
    """Handles password hashing and verification using bcrypt."""

    @staticmethod
    def hash(password: str) -> str:
        """Hash a plaintext password.

        Args:
            password: The plaintext password to hash.

        Returns:
            The bcrypt-hashed password string.
        """
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify(password: str, hashed: str) -> bool:
        """Verify a plaintext password against a bcrypt hash.

        Args:
            password: The plaintext password to check.
            hashed: The bcrypt hash to check against.

        Returns:
            True if the password matches the hash.
        """
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
