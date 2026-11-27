'''
File:   admin_api.py
Brief:  Admin-only endpoints for usage, users and settings.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.2.0

Provides the ``/api/admin`` router with usage totals/recent queries, user
CRUD, and LLM settings management (GET masked / PUT to update).
'''

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from mechanic.api.deps import get_app_settings, get_hub, require_admin
from mechanic.services.app_settings import effective_llm_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUserRequest(BaseModel):
    """Create-user request body.

    Attributes:
        username: Desired user name.
        password: Plain-text password (minimum 8 characters).
        role: Role string ("user" or "admin").
    """

    username: str
    password: str
    role: str


class ChangePasswordAdminRequest(BaseModel):
    """Admin password-change request body.

    Attributes:
        new_password: New plain-text password (minimum 8 characters).
    """

    new_password: str


class LlmSettingsUpdate(BaseModel):
    """LLM settings update body.

    Attributes:
        protocol: Provider protocol identifier.
        base_url: API base URL.
        api_key: Bearer token (empty string means keep stored value).
        model: Model identifier.
        temperature: Sampling temperature.
        max_output_tokens: Optional output token cap.
    """

    protocol: str | None = None
    base_url: str | None = None
    api_key: str = ""
    model: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None


def _mask_api_key(api_key: str) -> str:
    """Mask an API key, keeping first 6 and last 4 characters.

    Args:
        api_key: The raw API key string.

    Returns:
        Masked key with middle replaced by ellipsis.
    """
    if len(api_key) <= 12:
        return "***"
    return api_key[:6] + "…" + api_key[-4:]


@router.get("/usage/totals")
async def usage_totals(admin=Depends(require_admin)) -> dict:
    """Return aggregate request/token usage totals."""
    hub = get_hub()
    return hub.usage.totals().model_dump()


@router.get("/usage/recent")
async def usage_recent(
    limit: int = Query(default=50),
    admin=Depends(require_admin),
) -> list[dict]:
    """Return recent request log entries."""
    hub = get_hub()
    clamped = max(1, min(limit, 200))
    records = hub.usage.recent(clamped)
    return [r.model_dump() for r in records]


@router.get("/usage/{row_id}/detail")
async def usage_detail(
    row_id: int,
    admin=Depends(require_admin),
) -> dict:
    """Return the detail dict for a specific usage log row."""
    hub = get_hub()
    detail = hub.usage.get_detail(row_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail="запись не найдена или детализация отсутствует",
        )
    return detail


@router.get("/users")
async def list_users(admin=Depends(require_admin)) -> list[dict]:
    """Return all registered users."""
    hub = get_hub()
    users = hub.auth.list_users()
    return [u.model_dump() for u in users]


@router.post("/users")
async def create_user(
    body: CreateUserRequest, admin=Depends(require_admin)
) -> dict:
    """Create a new user account."""
    hub = get_hub()
    try:
        hub.auth.create_user(body.username, body.password, body.role)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.delete("/users/{username}")
async def delete_user(
    username: str, admin=Depends(require_admin)
) -> dict:
    """Delete a user account."""
    hub = get_hub()
    try:
        hub.auth.delete_user(username)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/users/{username}/password")
async def change_password_admin(
    username: str,
    body: ChangePasswordAdminRequest,
    admin=Depends(require_admin),
) -> dict:
    """Reset a user's password (admin)."""
    hub = get_hub()
    try:
        hub.auth.change_password_admin(username, body.new_password)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.get("/settings/llm")
async def get_llm_settings(admin=Depends(require_admin)) -> dict:
    """Return the effective LLM config with a masked API key."""
    hub = get_hub()
    cfg = effective_llm_config(hub.settings, get_app_settings())
    data = cfg.model_dump()
    data["api_key"] = _mask_api_key(data["api_key"])
    return data


@router.put("/settings/llm")
async def update_llm_settings(
    body: LlmSettingsUpdate, admin=Depends(require_admin)
) -> dict:
    """Update the stored LLM settings.

    An empty ``api_key`` means "keep the current stored value".
    """
    hub = get_hub()
    db = get_app_settings()

    # Get current stored values.
    current = db.get("llm") or {}

    # Build the merge: apply non-None fields from the request body.
    merged = dict(current)
    if body.protocol is not None:
        merged["protocol"] = body.protocol
    if body.base_url is not None:
        merged["base_url"] = body.base_url
    if body.api_key != "":
        merged["api_key"] = body.api_key
    elif "api_key" not in merged and body.api_key == "":
        pass  # keep stored value when api_key is empty string
    if body.model is not None:
        merged["model"] = body.model
    if body.temperature is not None:
        merged["temperature"] = body.temperature
    if body.max_output_tokens is not None:
        merged["max_output_tokens"] = body.max_output_tokens

    db.set("llm", merged)

    # Return masked view.
    cfg = effective_llm_config(hub.settings, db)
    data = cfg.model_dump()
    data["api_key"] = _mask_api_key(data["api_key"])
    return data


@router.get("/alerts")
async def list_alerts(
    limit: int = 50, admin=Depends(require_admin)
) -> list[dict]:
    """List recent admin alerts (newest first)."""
    capped = min(max(limit, 1), 200)
    return [r.model_dump() for r in get_hub().alerts.recent(capped)]


@router.get("/alerts/unread_count")
async def alerts_unread_count(admin=Depends(require_admin)) -> dict:
    """Count unread admin alerts (for the nav badge)."""
    return {"unread": get_hub().alerts.unread_count()}


@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(
    alert_id: int, admin=Depends(require_admin)
) -> dict:
    """Mark one admin alert as read."""
    if not get_hub().alerts.mark_read(alert_id):
        raise HTTPException(status_code=404, detail="оповещение не найдено")
    return {"status": "ok"}
