'''
File:   auth_api.py
Brief:  Authentication endpoints (login, change password, me).
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Provides the ``/api/auth`` router with login, password change and current-user
introspection endpoints backed by :class:`~mechanic.services.auth.AuthService`.
'''

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from mechanic.api.deps import get_hub
from mechanic.services.auth import AuthError, TokenUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Login request body.

    Attributes:
        username: User name.
        password: Plain-text password.
    """

    username: str
    password: str


async def _auth_user(request: Request) -> TokenUser:
    """Resolve the bearer token to a :class:`TokenUser`.

    Args:
        request: FastAPI request object.

    Returns:
        Resolved :class:`TokenUser`.

    Raises:
        HTTPException(401): If the token is invalid or unknown.
    """
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="требуется авторизация",
        )
    token = auth_header[7:]
    user = get_hub().auth.resolve_token(token)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="требуется авторизация",
        )
    return user


@router.post("/login")
async def login(body: LoginRequest) -> dict:
    """Authenticate a user and return a session token."""
    hub = get_hub()
    result = hub.auth.verify_login(body.username, body.password)
    if result is None:
        raise HTTPException(
            status_code=401,
            detail="неверное имя пользователя или пароль",
        )
    token = hub.auth.create_token(body.username)
    return {
        "token": token,
        "username": result.username,
        "role": result.role,
        "must_change_password": result.must_change_password,
    }


class ChangePasswordRequest(BaseModel):
    """Change-password request body.

    Attributes:
        old_password: Current password (must match).
        new_password: New password (minimum 8 characters).
    """

    old_password: str
    new_password: str


@router.post("/change_password")
async def change_password(
    body: ChangePasswordRequest,
    user: TokenUser = Depends(_auth_user),
) -> dict:
    """Change the authenticated user's password."""
    hub = get_hub()
    try:
        hub.auth.change_password(user.username, body.old_password, body.new_password)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.get("/me")
async def me(user: TokenUser = Depends(_auth_user)) -> dict:
    """Return the authenticated user's profile."""
    return {
        "username": user.username,
        "role": user.role,
        "must_change_password": user.must_change_password,
    }
