"""SQLite user database - lightweight persistence for auth data."""

from __future__ import annotations

import contextlib
import os
import sqlite3
import stat
import threading
from datetime import datetime
from pathlib import Path

from .models import User


class UserDatabase:
    """SQLite-backed user storage.

    Uses Python's built-in sqlite3 module - no external ORM required.
    Maintains a single connection for the lifetime of the instance.

    The single connection is shared across (potentially concurrent) async
    request handlers, so it is opened with ``check_same_thread=False`` and every
    access is serialized through ``self._lock`` to avoid interleaved writes and
    ``sqlite3.ProgrammingError`` / "database is locked" errors under load.
    """

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_schema()
        # Restrict the on-disk auth DB (bcrypt password hashes) to the owner.
        if self.db_path != ":memory:":
            with contextlib.suppress(OSError):
                os.chmod(self.db_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        # Set on both the normal ``__init__`` path and the ``__new__`` path used
        # by the live API (which wires its own connection then calls this).
        if not hasattr(self, "_lock"):
            self._lock = threading.RLock()
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users (username)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)"
        )
        self._conn.commit()

    def create_user(self, user: User) -> User:
        """Insert a new user into the database.

        Args:
            user: The User object to persist.

        Returns:
            The persisted User object.

        Raises:
            ValueError: If username or email already exists.
        """
        try:
            with self._lock:
                self._conn.execute(
                    """INSERT INTO users
                       (id, username, email, hashed_password, role, is_active, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        user.id,
                        user.username,
                        user.email,
                        user.hashed_password,
                        user.role.value,
                        int(user.is_active),
                        user.created_at,
                        user.updated_at,
                    ),
                )
                self._conn.commit()
        except sqlite3.IntegrityError as e:
            error_msg = str(e).lower()
            if "username" in error_msg:
                raise ValueError(f"Username '{user.username}' already exists")
            if "email" in error_msg:
                raise ValueError(f"Email '{user.email}' already exists")
            raise ValueError(f"User already exists: {e}")
        return user

    def get_by_username(self, username: str) -> User | None:
        """Find a user by username."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        return User.from_row(row) if row else None

    def get_by_id(self, user_id: str) -> User | None:
        """Find a user by ID."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return User.from_row(row) if row else None

    def get_by_email(self, email: str) -> User | None:
        """Find a user by email."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
        return User.from_row(row) if row else None

    def update_user(self, user: User) -> bool:
        """Update an existing user.

        Returns:
            True if the user was updated, False if not found.
        """
        user.updated_at = datetime.utcnow().isoformat()
        with self._lock:
            cursor = self._conn.execute(
                """UPDATE users SET
                   username = ?, email = ?, hashed_password = ?,
                   role = ?, is_active = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    user.username,
                    user.email,
                    user.hashed_password,
                    user.role.value,
                    int(user.is_active),
                    user.updated_at,
                    user.id,
                ),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def delete_user(self, user_id: str) -> bool:
        """Delete a user by ID.

        Returns:
            True if the user was deleted, False if not found.
        """
        with self._lock:
            cursor = self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            self._conn.commit()
        return cursor.rowcount > 0

    def list_users(self, active_only: bool = True) -> list[User]:
        """List all users."""
        query = "SELECT * FROM users"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(query).fetchall()
        return [User.from_row(row) for row in rows]

    def count_users(self) -> int:
        """Return total number of users."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM users").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
