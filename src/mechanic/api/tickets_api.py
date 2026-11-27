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
from shared.models import SessionCheck, TicketPayload

from mechanic.api.deps import get_hub
from mechanic.config import get_settings
from mechanic.errors import MockApiError
from mechanic.services.fleet import FleetError

logger = logging.getLogger(__name__)


class TicketSubmitRequest(TicketPayload):
    '''Submit body: ticket payload plus the mechanic's explicit override.

    ``override_confirmed`` is required True for sessions with
    ``signal_quality == "warning"`` (mechanic consciously confirmed the
    ticket after the recording-quality warning).
    '''

    override_confirmed: bool = False


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
    payload: TicketSubmitRequest,
    user=Depends(_auth_user),
) -> dict:
    """Submit a defect-inspection ticket to the Mock TOiR service."""
    hub = get_hub()

    # Quality gate (customer rules: bad / below-floor → never; warning →
    # only after the mechanic's explicit confirmation).
    session: SessionCheck | None = None
    try:
        session = hub.fleet.get_session(payload.vehicle_id, payload.session_id)
    except FleetError:
        session = None  # unknown session → gate skipped
    override_used = False
    if session is not None:
        floor = get_settings().confidence_ticket_floor
        confidence = session.confidence
        if session.signal_quality == "bad":
            raise HTTPException(
                status_code=422,
                detail="качество записи bad — заявка недоступна, повторите запись",
            )
        if confidence is not None and confidence < floor:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"уверенность {confidence} ниже порога {floor} — "
                    "заявка недоступна, повторите запись"
                ),
            )
        if session.signal_quality == "warning":
            if not payload.override_confirmed:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "качество записи с предупреждением — подтвердите "
                        "заявку чекбоксом в форме или повторите запись"
                    ),
                )
            override_used = True

    # Build a clean TicketPayload for everything downstream (TOiR, ticket_log).
    clean_payload = TicketPayload(
        **payload.model_dump(exclude={"override_confirmed"})
    )

    try:
        result = await hub.toir.submit_ticket(clean_payload)
    except MockApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    hub.ticket_log.add(result, clean_payload, username=user.username)
    hub.usage.record(
        username=user.username,
        kind="ticket_submit",
        vehicle_id=payload.vehicle_id,
        status="ok",
        detail=(
            {
                "override_confirmed": True,
                "signal_quality": session.signal_quality,
                "confidence": session.confidence,
            }
            if override_used
            else None
        ),
    )
    return {
        "ticket_id": result.ticket_id,
        "status": result.status,
        "ticket_record": {
            "ticket_id": result.ticket_id,
            "vehicle_id": clean_payload.vehicle_id,
            "session_id": clean_payload.session_id,
            "anomaly_type": clean_payload.anomaly_type,
            "urgency": clean_payload.urgency,
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
