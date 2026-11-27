"""
File:   test_auth.py
Brief:  Tests for AuthService — users, tokens and roles.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
"""

from __future__ import annotations

import pytest

from mechanic.services.auth import AuthError, AuthService


class TestAuthServiceBootstrapAdmin:
    """Test bootstrap_admin()."""

    def test_bootstrap_returns_password(self, tmp_path: pytest.TempPath) -> None:
        """bootstrap_admin() returns a plaintext password for the first call."""
        auth = AuthService(tmp_path / "auth.db")
        pw = auth.bootstrap_admin()

        assert pw is not None
        assert len(pw) >= 12  # secrets.token_urlsafe(12) → 16 chars

    def test_bootstrap_second_call_returns_none(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """bootstrap_admin() returns None when admin already exists."""
        auth = AuthService(tmp_path / "auth.db")
        pw1 = auth.bootstrap_admin()
        pw2 = auth.bootstrap_admin()

        assert pw1 is not None
        assert pw2 is None

    def test_bootstrap_admin_uses_initial_password(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """bootstrap_admin(initial_password) uses the supplied password."""
        auth = AuthService(tmp_path / "auth.db")
        pw = auth.bootstrap_admin("startup-pass-1")

        assert pw == "startup-pass-1"

        result = auth.verify_login("admin", "startup-pass-1")
        assert result is not None
        assert result.username == "admin"
        assert result.role == "admin"

        # Second call returns None (admin already exists).
        pw2 = auth.bootstrap_admin("another-pass")
        assert pw2 is None

    def test_bootstrap_admin_generates_when_unset(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """bootstrap_admin() with no args generates a random password."""
        auth = AuthService(tmp_path / "auth.db")
        pw = auth.bootstrap_admin()

        assert pw is not None
        assert len(pw) >= 12

        result = auth.verify_login("admin", pw)
        assert result is not None
        assert result.username == "admin"


class TestAuthServiceVerifyLogin:
    """Test verify_login()."""

    def test_verify_ok(self, tmp_path: pytest.TempPath) -> None:
        """verify_login() returns LoginResult for correct credentials."""
        auth = AuthService(tmp_path / "auth.db")
        bootstrap_pw = auth.bootstrap_admin()
        assert bootstrap_pw is not None

        result = auth.verify_login("admin", bootstrap_pw)
        assert result is not None
        assert result.username == "admin"
        assert result.role == "admin"

    def test_verify_wrong_password(self, tmp_path: pytest.TempPath) -> None:
        """verify_login() returns None for wrong password."""
        auth = AuthService(tmp_path / "auth.db")
        auth.bootstrap_admin()

        # Use a known password that won't match the bootstrap admin's
        result = auth.verify_login("admin", "completely_wrong_password_1234567890")
        assert result is None


class TestAuthServiceTokenRoundTrip:
    """Test create_token() and resolve_token() round-trip."""

    def test_token_resolve_roundtrip(self, tmp_path: pytest.TempPath) -> None:
        """create_token + resolve_token returns the original user info."""
        auth = AuthService(tmp_path / "auth.db")
        auth.bootstrap_admin()

        token = auth.create_token("admin")
        resolved = auth.resolve_token(token)

        assert resolved is not None
        assert resolved.username == "admin"
        assert resolved.role == "admin"

    def test_resolve_token_garbage(self, tmp_path: pytest.TempPath) -> None:
        """resolve_token('garbage') returns None for unknown token."""
        auth = AuthService(tmp_path / "auth.db")
        auth.bootstrap_admin()

        resolved = auth.resolve_token("garbage")
        assert resolved is None

    def test_expired_token_is_refused(self, tmp_path: pytest.TempPath) -> None:
        """A token created with a negative TTL must not resolve."""
        auth = AuthService(tmp_path / "auth.db")
        auth.bootstrap_admin()

        token = auth.create_token("admin", ttl_hours=-1)
        assert auth.resolve_token(token) is None


class TestAuthServiceChangePassword:
    """Test change_password() flow."""

    def test_change_password_flow(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """change_password sets must_change_password=0 and old password stops."""
        auth = AuthService(tmp_path / "auth.db")
        bootstrap_pw = auth.bootstrap_admin()
        assert bootstrap_pw is not None

        # Change password to a known value
        auth.change_password("admin", bootstrap_pw, "newpassword1")

        # New password works and must_change_password is False
        result = auth.verify_login("admin", "newpassword1")
        assert result is not None
        assert result.must_change_password is False

        # Old bootstrap password no longer works
        old_result = auth.verify_login("admin", bootstrap_pw)
        assert old_result is None


class TestAuthServiceCreateUser:
    """Test create_user() error cases."""

    def test_duplicate_username_raises(self, tmp_path: pytest.TempPath) -> None:
        """create_user raises AuthError on duplicate username."""
        auth = AuthService(tmp_path / "auth.db")
        auth.bootstrap_admin()

        auth.create_user("newuser", "password1234", "user")

        with pytest.raises(AuthError, match="already exists"):
            auth.create_user("newuser", "password1234", "user")

    def test_short_password_raises(self, tmp_path: pytest.TempPath) -> None:
        """create_user raises AuthError on password shorter than 8 chars."""
        auth = AuthService(tmp_path / "auth.db")
        auth.bootstrap_admin()

        with pytest.raises(AuthError, match="at least 8"):
            auth.create_user("shortpw", "short", "user")


class TestAuthServiceDeleteUser:
    """Test delete_user() behavior."""

    def test_delete_last_admin_refused(self, tmp_path: pytest.TempPath) -> None:
        """delete_user refuses to delete the last admin."""
        auth = AuthService(tmp_path / "auth.db")
        auth.bootstrap_admin()

        with pytest.raises(AuthError, match="last admin"):
            auth.delete_user("admin")

    def test_delete_user_and_verify_none(self, tmp_path: pytest.TempPath) -> None:
        """delete_user + verify_login returns None for deleted user."""
        auth = AuthService(tmp_path / "auth.db")
        auth.bootstrap_admin()

        # Create a regular user then delete them
        auth.create_user("tempuser", "password1234", "user")
        auth.delete_user("tempuser")

        result = auth.verify_login("tempuser", "password1234")
        assert result is None
