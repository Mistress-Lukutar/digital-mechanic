'''
File:   vehicles_api.py
Brief:  Vehicle listing, detail and fleet statistics endpoints.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Provides the ``/api`` router routes for vehicle data (list, detail) and
fleet-wide aggregate views (stats, priority vehicles).
'''

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from mechanic.api.deps import get_hub
from mechanic.errors import FleetError
from mechanic.services.auth import TokenUser
from mechanic.services.fleet import VehicleSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["vehicles"])


async def _auth_user(request: Request) -> TokenUser:
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


@router.get("/vehicles")
async def list_vehicles(
    query: str = Query(default=""),
    group: str | None = Query(default=None),
    user: TokenUser = Depends(_auth_user),
) -> list[dict]:
    """List vehicles with optional query and group filters."""
    hub = get_hub()
    summaries: list[VehicleSummary] = hub.fleet.list_vehicles(
        query=query or None,
        group=group if group in ("normal", "attention", "quarantine") else None,
    )
    return [s.model_dump() for s in summaries]


@router.get("/vehicles/{vehicle_id}")
async def get_vehicle_detail(
    vehicle_id: str,
    user: TokenUser = Depends(_auth_user),
) -> dict:
    """Return full detail for a single vehicle."""
    hub = get_hub()
    try:
        vehicle = hub.fleet.get_vehicle(vehicle_id)
    except FleetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    sessions_desc = hub.fleet.sessions_desc(vehicle_id)
    tickets = hub.ticket_log.list_by_vehicle(vehicle_id)

    return {
        "vehicle_id": vehicle.vehicle_id,
        "garage_no": vehicle.garage_no,
        "make": vehicle.make,
        "model": vehicle.model,
        "vehicle_type": vehicle.vehicle_type,
        "engine_model": vehicle.engine_model,
        "fuel": vehicle.fuel,
        "sessions": [s.model_dump() for s in sessions_desc],
        "tickets": [
            {
                "ticket_id": t.ticket_id,
                "created_at": t.created_at.isoformat(),
                "payload": t.payload.model_dump(),
            }
            for t in tickets
        ],
    }


@router.get("/fleet/stats")
async def fleet_stats(
    user: TokenUser = Depends(_auth_user),
) -> dict:
    """Return aggregate fleet statistics."""
    hub = get_hub()
    stats = hub.fleet.fleet_stats()
    return stats.model_dump()


@router.get("/fleet/priority")
async def fleet_priority(
    user: TokenUser = Depends(_auth_user),
) -> list[dict]:
    """Return priority (quarantine) vehicles sorted by anomaly score."""
    hub = get_hub()
    vehicles = hub.fleet.priority_vehicles()
    return [v.model_dump() for v in vehicles]
