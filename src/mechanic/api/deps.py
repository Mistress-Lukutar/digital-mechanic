'''
File:   deps.py
Brief:  FastAPI dependency functions for hub, auth and conversations.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Provides module-level singletons for the service hub and app-settings store,
plus ``Depends``-compatible async callables that FastAPI uses for dependency
injection on every request (auth token resolution, admin gate, conversation
store access).
'''

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mechanic.agent.conversations import ConversationStore
from mechanic.config import Settings
from mechanic.services.app_settings import AppSettings
from mechanic.services.auth import TokenUser
from mechanic.services.hub import ServiceHub, build_service_hub

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hub singleton.
# ---------------------------------------------------------------------------

_hub: ServiceHub | None = None


def init_hub(settings: Settings) -> ServiceHub:
    """Build and store the global :class:`ServiceHub`.

    Args:
        settings: Application settings used to wire all services.

    Returns:
        The newly constructed ``ServiceHub`` (also stored globally).
    """
    global _hub
    # Close the old hub's connections before replacing it.
    if _hub is not None:
        try:
            _hub.auth._conn.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            _hub.ticket_log._conn.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            _hub.usage._conn.close()
        except Exception:  # noqa: BLE001
            pass
    _hub = build_service_hub(settings)
    return _hub


def get_hub() -> ServiceHub:
    """Return the initialised hub or raise ``RuntimeError``.

    Returns:
        The process-wide :class:`ServiceHub` instance.

    Raises:
        RuntimeError: If :func:`init_hub` has not been called yet.
    """
    if _hub is None:
        raise RuntimeError("hub not initialised")
    return _hub


# ---------------------------------------------------------------------------
# AppSettings singleton (separate from the hub to allow test overrides).
# ---------------------------------------------------------------------------

_app_settings: AppSettings | None = None


def init_app_settings(settings: Settings) -> AppSettings:
    """Build and store the global :class:`AppSettings` instance.

    Args:
        settings: Application settings; ``db_path`` is used to locate the DB.

    Returns:
        The newly constructed ``AppSettings`` (also stored globally).
    """
    global _app_settings
    if _app_settings is not None:
        try:
            _app_settings._conn.close()
        except Exception:  # noqa: BLE001
            pass
    _app_settings = AppSettings(settings.resolve_db_path())
    return _app_settings


def get_app_settings() -> AppSettings:
    """Return the initialised app-settings store or raise ``RuntimeError``.

    Returns:
        The process-wide :class:`AppSettings` instance.

    Raises:
        RuntimeError: If :func:`init_app_settings` has not been called yet.
    """
    if _app_settings is None:
        raise RuntimeError("app_settings not initialised")
    return _app_settings


# ---------------------------------------------------------------------------
# Auth dependencies.
# ---------------------------------------------------------------------------

_security = HTTPBearer()


async def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> TokenUser:
    """Resolve the bearer token to a :class:`TokenUser`.

    Extracts the ``Authorization`` header, looks up the token via the hub's
    auth service and raises ``401`` on missing/malformed/unknown tokens.

    Args:
        credentials: FastAPI-injected Bearer credentials.

    Returns:
        Resolved :class:`TokenUser`.

    Raises:
        HTTPException(401): If the token is invalid or unknown.
    """
    token = credentials.credentials
    user = get_hub().auth.resolve_token(token)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="требуется авторизация",
        )
    return user


async def require_admin(user: TokenUser = Depends(current_user)) -> TokenUser:
    """Gate that requires the ``admin`` role.

    Args:
        user: Resolved current user from :func:`current_user`.

    Returns:
        The same :class:`TokenUser` if they are an admin.

    Raises:
        HTTPException(403): If the user lacks admin privileges.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="нужны права администратора",
        )
    return user


# ---------------------------------------------------------------------------
# Conversation store singleton.
# ---------------------------------------------------------------------------

_conversations: ConversationStore | None = None


def get_conversations() -> ConversationStore:
    """Return the module-level :class:`ConversationStore` singleton.

    Creates it on first call if needed.

    Returns:
        The process-wide conversation store.
    """
    global _conversations
    if _conversations is None:
        _conversations = ConversationStore()
    return _conversations
