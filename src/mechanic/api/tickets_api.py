'''
File:   tickets_api.py
Brief:  Ticket submission and listing endpoints.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Provides the ``/api/tickets`` router with a ticket submission endpoint that
posts to the Mock TOiR service and a list-by-vehicle endpoint returning
locally stored ticket records.
'''

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from shared.models import TicketPayload

from mechanic.api.deps import get_hub
from mechanic.errors import MockApiError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


async def _auth_user(request: Request) -> object:  # TokenUser
    """Resolve bearer token to :class:`TokenUser`."""
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


@router.post("")
async def submit_ticket(
    payload: TicketPayload,
    user=Depends(_auth_user),
) -> dict:
    """Submit a defect-inspection ticket to the Mock TOiR service."""
    hub = get_hub()
    try:
        result = await hub.toir.submit_ticket(payload)
    except MockApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    hub.ticket_log.add(result, payload, username=user.username)
    hub.usage.record(
        username=user.username,
        kind="ticket_submit",
        vehicle_id=payload.vehicle_id,
        status="ok",
    )
    return {
        "ticket_id": result.ticket_id,
        "status": result.status,
        "ticket_record": {
            "ticket_id": result.ticket_id,
            "vehicle_id": payload.vehicle_id,
            "session_id": payload.session_id,
            "anomaly_type": payload.anomaly_type,
            "urgency": payload.urgency,
        },
    }


@router.get("/{vehicle_id}")
async def list_tickets(
    vehicle_id: str,
    user=Depends(_auth_user),
) -> list[dict]:
    """Return all locally stored tickets for *vehicle_id*."""
    hub = get_hub()
    records = hub.ticket_log.list_by_vehicle(vehicle_id)
    return [
        {
            "ticket_id": r.ticket_id,
            "created_at": r.created_at.isoformat(),
            "payload": r.payload.model_dump(),
        }
        for r in records
    ]
