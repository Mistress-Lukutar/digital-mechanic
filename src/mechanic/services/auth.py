"""
File:   auth.py
Brief:  Users, tokens and roles backed by SQLite.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Provides user authentication (pbkdf2_hmac passwords), opaque session
tokens with expiry, and admin bootstrap for initial deployment.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from mechanic.errors import MechanicError


class AuthError(MechanicError):
    """Raised on authentication/authorisation failures."""


class LoginResult(BaseModel):
    """Result of a successful login.

    Attributes:
        username: The authenticated user name.
        role: User role string ("user" or "admin").
        must_change_password: Whether the password needs to be changed on next login.
    """

    username: str
    role: str
    must_change_password: bool


class TokenUser(BaseModel):
    """Decoded token payload.

    Attributes:
        username: The user associated with the token.
        role: User role string.
        must_change_password: Whether the password needs to be changed.
    """

    username: str
    role: str
    must_change_password: bool


class UserRow(BaseModel):
    """User row returned by list_users.

    Attributes:
        username: The user name.
        role: User role string.
        must_change_password: Whether the password needs to be changed.
        created_at: ISO 8601 creation timestamp.
    """

    username: str
    role: str
    must_change_password: bool
    created_at: str


class AuthService:
    """User authentication and token management service.

    All passwords are stored as hex-encoded PBKDF2-HMAC-SHA256 hashes
    with a random salt and 200 000 iterations.

    Args:
        db_path: Filesystem path where the SQLite database will reside.
            Parent directories are created automatically if missing.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialise the auth database.

        Creates parent directories, opens a connection with WAL journal mode,
        and creates the ``users`` and ``tokens`` tables if they do not exist.

        Args:
            db_path: Destination path for the SQLite database file.
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_tables()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_tables(self) -> None:
        """Create the ``users`` and ``tokens`` tables if missing."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username                 TEXT PRIMARY KEY,
                password_hash            TEXT NOT NULL,
                salt                     TEXT NOT NULL,
                role                     TEXT NOT NULL CHECK(role IN ('user', 'admin')),
                must_change_password     INTEGER DEFAULT 0,
                created_at               TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                token       TEXT PRIMARY KEY,
                username    TEXT NOT NULL,
                expires_at  TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tokens_username ON tokens(username)"
        )
        self._conn.commit()

    @staticmethod
    def _hash_password(password: str, salt_hex: str) -> str:
        """Hash *password* with the given hex-encoded salt.

        Args:
            password: Plain-text password.
            salt_hex: Hex-encoded salt bytes.

        Returns:
            Hex-encoded PBKDF2-HMAC-SHA256 hash string.
        """
        salt_bytes = bytes.fromhex(salt_hex)
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt_bytes, 200_000
        ).hex()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def bootstrap_admin(self, initial_password: str | None = None) -> str | None:
        """Create the initial admin user if none exists.

        Creates a user named ``"admin"`` with role ``"admin"``,
        ``must_change_password=1``, and a random 16-char password
        (``secrets.token_urlsafe(12)`` produces 16 URL-safe chars), or the
        supplied *initial_password* when given.

        Args:
            initial_password: When given, used as the initial admin password
                instead of a generated one; the caller decides whether it may
                be logged.

        Returns:
            The plaintext password if a new admin was created, or ``None``
            if an admin user already exists.

        Raises:
            sqlite3.IntegrityError: On unexpected database errors.
        """
        cursor = self._conn.execute(
            "SELECT 1 FROM users WHERE role = 'admin' LIMIT 1"
        )
        if cursor.fetchone() is not None:
            return None

        password = initial_password or secrets.token_urlsafe(12)
        salt = secrets.token_hex(16)
        pw_hash = self._hash_password(password, salt)
        now = datetime.now(UTC).isoformat()

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO users (username, password_hash, salt, role,
                                   must_change_password, created_at)
                VALUES (?, ?, ?, 'admin', 1, ?)
                """,
                ("admin", pw_hash, salt, now),
            )
            self._conn.commit()

        return password

    def verify_login(self, username: str, password: str) -> LoginResult | None:
        """Verify a username/password pair.

        Args:
            username: The user name to look up.
            password: Plain-text password to check.

        Returns:
            :class:`LoginResult` on success, or ``None`` if the credentials
            are wrong or the user does not exist.
        """
        cursor = self._conn.execute(
            "SELECT password_hash, salt, role, must_change_password "
            "FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        expected = row["password_hash"]
        computed = self._hash_password(password, row["salt"])
        if not hmac.compare_digest(computed, expected):
            return None

        return LoginResult(
            username=username,
            role=row["role"],
            must_change_password=bool(row["must_change_password"]),
        )

    def create_token(self, username: str, ttl_hours: int = 168) -> str:
        """Create a new opaque session token for *username*.

        Args:
            username: The user to issue the token for.
            ttl_hours: Token lifetime in hours. Defaults to 168 (one week).

        Returns:
            A URL-safe random hex token string.
        """
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO tokens (token, username, expires_at)
                VALUES (?, ?, ?)
                """,
                (token, username, expires_at.isoformat()),
            )
            self._conn.commit()

        return token

    def resolve_token(self, token: str) -> TokenUser | None:
        """Resolve a token to its associated user.

        Expired tokens are deleted lazily on lookup.

        Args:
            token: The opaque session token string.

        Returns:
            :class:`TokenUser` if the token is valid and not expired,
            or ``None`` if unknown/expired/revoked.
        """
        with self._lock:
            now_iso = datetime.now(UTC).isoformat()
            cursor = self._conn.execute(
                "SELECT username, expires_at FROM tokens WHERE token = ?", (token,)
            )
            row = cursor.fetchone()
            if row is None:
                return None
            if row["expires_at"] < now_iso:
                # Expired: drop it lazily and refuse the token.
                self._conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
                self._conn.commit()
                return None

        user_cursor = self._conn.execute(
            "SELECT username, role, must_change_password FROM users WHERE username = ?",
            (row["username"],),
        )
        user_row = user_cursor.fetchone()
        if user_row is None:
            return None

        return TokenUser(
            username=user_row["username"],
            role=user_row["role"],
            must_change_password=bool(user_row["must_change_password"]),
        )

    def change_password(
        self, username: str, old: str, new: str
    ) -> None:
        """Change a user's password after verifying the old one.

        Args:
            username: The user whose password to change.
            old: Current plain-text password (must match).
            new: New plain-text password (minimum 8 characters).

        Raises:
            AuthError: If the old password is wrong or the new password
                is shorter than 8 characters.
        """
        if len(new) < 8:
            raise AuthError("New password must be at least 8 characters")

        cursor = self._conn.execute(
            "SELECT password_hash, salt FROM users WHERE username = ?", (username,)
        )
        row = cursor.fetchone()
        if row is None:
            raise AuthError(f"User '{username}' not found")

        expected = row["password_hash"]
        computed = self._hash_password(old, row["salt"])
        if not hmac.compare_digest(computed, expected):
            raise AuthError("Old password does not match")

        new_salt = secrets.token_hex(16)
        new_hash = self._hash_password(new, new_salt)

        with self._lock:
            self._conn.execute(
                """
                UPDATE users SET password_hash = ?, salt = ?, must_change_password = 0
                WHERE username = ?
                """,
                (new_hash, new_salt, username),
            )
            self._conn.commit()

    def change_password_admin(self, username: str, new: str) -> None:
        """Admin-initiated password reset for *username*.

        Sets ``must_change_password=1`` so the user must change it on next
        login.

        Args:
            username: The user whose password to reset.
            new: New plain-text password (minimum 8 characters).

        Raises:
            AuthError: If the user does not exist or the new password is too short.
        """
        if len(new) < 8:
            raise AuthError("New password must be at least 8 characters")

        cursor = self._conn.execute(
            "SELECT username FROM users WHERE username = ?", (username,)
        )
        if cursor.fetchone() is None:
            raise AuthError(f"User '{username}' not found")

        new_salt = secrets.token_hex(16)
        new_hash = self._hash_password(new, new_salt)

        with self._lock:
            self._conn.execute(
                """
                UPDATE users SET password_hash = ?, salt = ?, must_change_password = 1
                WHERE username = ?
                """,
                (new_hash, new_salt, username),
            )
            self._conn.commit()

    def create_user(
        self, username: str, password: str, role: str
    ) -> None:
        """Create a new user account.

        Args:
            username: Desired user name (must be unique).
            password: Plain-text password (minimum 8 characters).
            role: Role string — must be ``"user"`` or ``"admin"``.

        Raises:
            AuthError: If the username already exists, the role is invalid,
                or the password is too short.
        """
        if len(password) < 8:
            raise AuthError("Password must be at least 8 characters")
        if role not in ("user", "admin"):
            raise AuthError(f"Invalid role '{role}': must be 'user' or 'admin'")

        cursor = self._conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        )
        if cursor.fetchone() is not None:
            raise AuthError(f"User '{username}' already exists")

        salt = secrets.token_hex(16)
        pw_hash = self._hash_password(password, salt)
        now = datetime.now(UTC).isoformat()

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO users (username, password_hash, salt, role,
                                   must_change_password, created_at)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (username, pw_hash, salt, role, now),
            )
            self._conn.commit()

    def delete_user(self, username: str) -> None:
        """Delete a user account.

        Refuses to delete the last admin user.

        Args:
            username: The user name to delete.

        Raises:
            AuthError: If the user does not exist or is the last admin.
        """
        cursor = self._conn.execute(
            "SELECT role FROM users WHERE username = ?", (username,)
        )
        row = cursor.fetchone()
        if row is None:
            raise AuthError(f"User '{username}' not found")

        # Refuse to delete the last admin
        if row["role"] == "admin":
            admin_cursor = self._conn.execute(
                "SELECT COUNT(*) AS cnt FROM users WHERE role = 'admin'"
            )
            admin_count = admin_cursor.fetchone()["cnt"]
            if admin_count <= 1:
                raise AuthError("Cannot delete the last admin user")

        with self._lock:
            self._conn.execute("DELETE FROM users WHERE username = ?", (username,))
            self._conn.commit()

    def list_users(self) -> list[UserRow]:
        """Return all registered users.

        Returns:
            List of :class:`UserRow` objects sorted by ``created_at`` ascending.
        """
        cursor = self._conn.execute(
            """
            SELECT username, role, must_change_password, created_at
            FROM users
            ORDER BY created_at ASC
            """
        )
        rows: list[UserRow] = []
        for r in cursor.fetchall():
            rows.append(
                UserRow(
                    username=r["username"],
                    role=r["role"],
                    must_change_password=bool(r["must_change_password"]),
                    created_at=r["created_at"],
                )
            )
        return rows
