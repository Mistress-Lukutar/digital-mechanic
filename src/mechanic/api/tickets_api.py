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
from shared.models import Reference, SessionCheck, TicketPayload

from mechanic.api.deps import get_hub
from mechanic.config import get_settings
from mechanic.errors import MockApiError
from mechanic.services.fleet import FleetError
from mechanic.services.priority import FUEL_COMPATIBLE_FUELS
from mechanic.services.rag_client import ManualManifest

logger = logging.getLogger(__name__)


class TicketSubmitRequest(TicketPayload):
    '''Submit body: ticket payload plus the mechanic's explicit override.

    ``override_confirmed`` is required True for sessions with
    ``signal_quality == "warning"`` (mechanic consciously confirmed the
    ticket after the recording-quality warning).
    '''

    override_confirmed: bool = False


def _validate_references(
    manifest: ManualManifest,
    engine_model: str | None,
    references: list[Reference],
    username: str,
) -> None:
    """Reject references that do not resolve to a real manual page."""
    for ref in references:
        doc = manifest.find(ref.manual)
        if doc is None:
            logger.warning(
                "reference manual %r not found in manifest (user %s)",
                ref.manual,
                username,
            )
            raise HTTPException(
                status_code=422,
                detail=f"ссылка на несуществующее руководство: {ref.manual}",
            )
        if ref.pdf_page > doc.pages:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"страница {ref.pdf_page} вне диапазона "
                    f"руководства {doc.doc_id} ({doc.pages} стр.)"
                ),
            )
        if engine_model is not None and engine_model not in doc.engines:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"руководство {doc.doc_id} не относится "
                    f"к двигателю ТС ({engine_model})"
                ),
            )


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
        # Deterministic status gate (ТЗ: сбой проверки → не диагностировать):
        # a check_failed session can never carry a ticket, no matter what
        # quality/confidence the record claims.
        if session.status == "check_failed":
            raise HTTPException(
                status_code=422,
                detail=(
                    "проверка завершилась сбоем записи (check_failed) — "
                    "заявка недоступна, повторите запись"
                ),
            )
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

    # Fetch the vehicle card once for fuel/reference checks.
    try:
        vehicle_card = hub.fleet.get_vehicle(payload.vehicle_id)
    except FleetError:
        vehicle_card = None  # unknown vehicle → fuel/reference engine checks skipped

    # Fuel-compatibility gate (mirror of the agent tool's check).
    required_fuel = FUEL_COMPATIBLE_FUELS.get(payload.anomaly_type)
    if required_fuel is not None and vehicle_card is not None:
        fuel = (vehicle_card.fuel or "").strip().lower()
        if fuel and required_fuel not in fuel:
            hub.alerts.add(
                kind="fuel_mismatch",
                text=(
                    f"Код {payload.anomaly_type} несовместим с топливом "
                    f"«{vehicle_card.fuel}» ТС {payload.vehicle_id} (сессия "
                    f"{payload.session_id}) — заявка отклонена на подаче."
                ),
                username=user.username,
                vehicle_id=payload.vehicle_id,
                session_id=payload.session_id,
                engine_model=vehicle_card.engine_model,
            )
            raise HTTPException(
                status_code=422,
                detail=(
                    f"код неисправности {payload.anomaly_type} противоречит "
                    f"карточке ТС (топливо: {vehicle_card.fuel}) — заявка "
                    "недоступна, сверьте диагностику и карточку машины"
                ),
            )

    # References validation (defense-in-depth).
    engine_model = vehicle_card.engine_model if vehicle_card is not None else None
    _validate_references(
        hub.manifest, engine_model, payload.references, user.username
    )

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

    if override_used:
        hub.alerts.add(
            kind="warning_override",
            text=(
                f"Механик {user.username} подтвердил заявку по ТС "
                f"{payload.vehicle_id} (сессия {payload.session_id}) при "
                f"качестве записи warning (confidence {session.confidence})."
            ),
            username=user.username,
            vehicle_id=payload.vehicle_id,
            session_id=payload.session_id,
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
